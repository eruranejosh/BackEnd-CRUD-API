# Import os so we can read settings from the .env file
import os

# Import json so we can write structured quarantine logs
import json

# Import datetime tools for timestamps in quarantine logs
from datetime import datetime, timezone

# Import FastAPI components for creating the API
from fastapi import FastAPI, HTTPException, Request

# Import JSONResponse so we can customize validation error responses
from fastapi.responses import JSONResponse

# Import RequestValidationError so we can handle invalid input ourselves
from fastapi.exceptions import RequestValidationError

# Import SQLModel for database models and database operations
from sqlmodel import Field, Session, SQLModel, create_engine, select

# Import dotenv so values from .env are loaded into the environment
from dotenv import load_dotenv

# Import our LLM property schemas
from src.llm.schema import PropertyInput, PropertyEnrichment

# Import the LLM service functions
from src.llm.service import (
    call_llm,
    parse_llm_response,
    validate_llm_response,
    repair_llm_response,
)


# Load variables from the .env file
load_dotenv()


# Create the FastAPI application
app = FastAPI()


# Define the database model for a task
class Task(SQLModel, table=True):

    # Automatically generated primary key
    id: int | None = Field(default=None, primary_key=True)

    # Store the task title
    title: str

    # Store whether the task has been completed
    done: bool = False


# Create the SQLite database engine
sqlite_file_name = "tasks.db"

# Build the SQLite connection string
sqlite_url = f"sqlite:///{sqlite_file_name}"

# Create the database engine
engine = create_engine(
    sqlite_url,
    echo=True,
)


def create_db_and_tables():
    # Create the database tables if they do not already exist
    SQLModel.metadata.create_all(engine)


def create_initial_tasks():
    # Open a database session
    with Session(engine) as session:

        # Check whether tasks already exist
        existing_task = session.exec(
            select(Task)
        ).first()

        # Only create sample tasks when the database is empty
        if existing_task is None:

            # Create the first sample task
            task_one = Task(
                title="Learn FastAPI",
                done=False,
            )

            # Create the second sample task
            task_two = Task(
                title="Build CRUD API",
                done=False,
            )

            # Add both tasks to the database session
            session.add(task_one)
            session.add(task_two)

            # Save the tasks to the database
            session.commit()


@app.on_event("startup")
def startup():
    # Create the database tables when the API starts
    create_db_and_tables()

    # Create initial sample tasks if needed
    create_initial_tasks()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    # Get the first validation error
    error = exc.errors()[0]

    # Get the field that caused the error
    field = error["loc"][-1]

    # Return a clear 400 response naming the invalid field
    return JSONResponse(
        status_code=400,
        content={
            "error": f"Invalid field: {field}",
            "message": error["msg"],
        },
    )


@app.get("/")
def root():
    # Return a simple message showing that the API is running
    return {
        "message": "Backend API is running"
    }


@app.get("/health")
def health():
    # Return a simple health-check response
    return {
        "status": "ok"
    }


@app.get("/tasks")
def get_tasks():
    # Open a database session
    with Session(engine) as session:

        # Retrieve all tasks from the database
        tasks = session.exec(
            select(Task)
        ).all()

        # Return the tasks
        return tasks


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    # Open a database session
    with Session(engine) as session:

        # Find the task using its ID
        task = session.get(
            Task,
            task_id,
        )

        # Return 404 if the task does not exist
        if task is None:
            raise HTTPException(
                status_code=404,
                detail="Task not found",
            )

        # Return the requested task
        return task


@app.post("/tasks")
def create_task(task: Task):
    # Open a database session
    with Session(engine) as session:

        # Add the new task to the database
        session.add(task)

        # Save the change
        session.commit()

        # Refresh the object so generated fields such as ID are available
        session.refresh(task)

        # Return the newly created task
        return task


@app.put("/tasks/{task_id}")
def update_task(
    task_id: int,
    task_update: Task,
):
    # Open a database session
    with Session(engine) as session:

        # Find the existing task
        task = session.get(
            Task,
            task_id,
        )

        # Return 404 if the task does not exist
        if task is None:
            raise HTTPException(
                status_code=404,
                detail="Task not found",
            )

        # Update the task title
        task.title = task_update.title

        # Update the completed status
        task.done = task_update.done

        # Save the changes
        session.add(task)
        session.commit()

        # Refresh the object with the latest database values
        session.refresh(task)

        # Return the updated task
        return task


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    # Open a database session
    with Session(engine) as session:

        # Find the task to delete
        task = session.get(
            Task,
            task_id,
        )

        # Return 404 if the task does not exist
        if task is None:
            raise HTTPException(
                status_code=404,
                detail="Task not found",
            )

        # Delete the task
        session.delete(task)

        # Save the deletion
        session.commit()

        # Return a confirmation message
        return {
            "message": "Task deleted successfully"
        }


def quarantine_failure(
    property_text: str,
    raw_response: str,
    validation_error: str,
    repair_error: str,
):
    # Define where failed LLM responses will be stored
    log_path = "logs/quarantine.jsonl"

    # Create a structured record containing failure information
    record = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),

        # Record which version of the prompt was used
        "prompt_version": "property-enrich-v1",

        # Store the original property input
        "input": property_text,

        # Store the raw LLM response for debugging
        "raw_response": raw_response,

        # Store the first validation/parsing error
        "validation_error": validation_error,

        # Store the error from the repair attempt
        "repair_error": repair_error,
    }

    # Open the quarantine file in append mode
    with open(
        log_path,
        "a",
        encoding="utf-8",
    ) as file:

        # Write one JSON object per line
        file.write(
            json.dumps(record) + "\n"
        )


@app.post(
    "/enrich",
    response_model=PropertyEnrichment,
)
def enrich_property(
    property_input: PropertyInput,
):

    # Check the kill switch before making any LLM request
    if os.getenv(
        "LLM_ENABLED",
        "true",
    ).lower() != "true":

        # Return a deterministic response without calling the LLM
        return PropertyEnrichment(
            property_type="other",
            bedrooms=None,
            location=None,
            condition="unknown",
            servicing="unknown",
            summary="LLM enrichment is currently disabled.",
            confidence=0.0,
            needs_review=True,
        )

    # Return a deterministic response when stub mode is enabled
    if os.getenv("LLM_STUB") == "1":

        # Return a response that is guaranteed to match our schema
        return PropertyEnrichment(
            property_type="other",
            bedrooms=None,
            location=None,
            condition="unknown",
            servicing="unknown",
            summary="Stub response for property enrichment.",
            confidence=0.0,
            needs_review=True,
        )

    # Send the property description to the LLM
    raw_response = call_llm(
        property_input.text
    )

    try:

        # Convert the LLM text response into a Python dictionary
        parsed_response = parse_llm_response(
            raw_response
        )

        # Validate the dictionary against our Pydantic schema
        validated_response = validate_llm_response(
            parsed_response
        )

        # Return only the validated response
        return validated_response

    except Exception as first_error:

        # Convert the first validation or parsing error into text
        validation_error = str(first_error)

        try:

            # Give the LLM exactly one opportunity to repair its response
            repaired_response = repair_llm_response(
                raw_response,
                validation_error,
            )

            # Parse the repaired response
            repaired_parsed_response = parse_llm_response(
                repaired_response
            )

            # Validate the repaired response
            repaired_validated_response = validate_llm_response(
                repaired_parsed_response
            )

            # Return the repaired and validated response
            return repaired_validated_response

        except Exception as repair_error:

            # Save the failed response and debugging information
            quarantine_failure(
                property_text=property_input.text,
                raw_response=raw_response,
                validation_error=validation_error,
                repair_error=str(repair_error),
            )

            # Return 422 without exposing the raw LLM response
            raise HTTPException(
                status_code=422,
                detail="LLM response could not be validated",
            )