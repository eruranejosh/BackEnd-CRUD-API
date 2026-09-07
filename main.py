# Import FastAPI tools used to build the API and handle HTTP requests
from fastapi import FastAPI, HTTPException, Request

# Import SQLModel tools used to store and retrieve data
from sqlmodel import SQLModel, Field, Session, create_engine, select

# Import Optional for fields that can contain None
from typing import Optional

# Import os so we can read environment variables
import os

# Import json so we can write structured quarantine records
import json

# Import datetime so we can record when a failure occurred
from datetime import datetime, timezone

# Import the schemas for property input and validated property output
from src.llm.schema import PropertyInput, PropertyEnrichment

# Import the functions that process, validate, and repair the LLM response
from src.llm.service import (
    call_llm,
    parse_llm_response,
    validate_llm_response,
    repair_llm_response,
)

# Import the validation error handler
from fastapi.exceptions import RequestValidationError

# Import JSONResponse so we can return a custom 400 response
from fastapi.responses import JSONResponse

# Import dotenv so variables from .env can be loaded
from dotenv import load_dotenv

# Import BaseModel for our existing task request models
from pydantic import BaseModel


# Load the .env file into the application environment
load_dotenv()


# Create the FastAPI application
app = FastAPI()


# =============================
# DATABASE CONFIGURATION
# =============================

# Define the database model for a task
class Task(SQLModel, table=True):

    # Automatically generated task ID
    id: Optional[int] = Field(default=None, primary_key=True)

    # Task title
    title: str

    # Whether the task has been completed
    done: bool = False


# Define the SQLite database file
sqlite_file_name = "tasks.db"

# Build the SQLite database connection URL
sqlite_url = f"sqlite:///{sqlite_file_name}"

# Create the database engine
engine = create_engine(
    sqlite_url,
    echo=False,
)


# Create the database tables
def create_db_and_tables():

    # Create all tables defined by SQLModel
    SQLModel.metadata.create_all(engine)


# Create initial tasks if the database is empty
def create_initial_tasks():

    # Open a database session
    with Session(engine) as session:

        # Check whether a task already exists
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
                title="Build an API",
                done=False,
            )

            # Add both tasks to the database
            session.add(task_one)
            session.add(task_two)

            # Save the changes
            session.commit()


# Run database setup when the application starts
@app.on_event("startup")
def startup_event():

    # Create the database tables
    create_db_and_tables()

    # Create initial tasks if needed
    create_initial_tasks()


# =============================
# REQUEST VALIDATION HANDLER
# =============================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):

    # Get the first validation error
    error = exc.errors()[0]

    # Get the field that caused the validation error
    field = error["loc"][-1]

    # Return a clear 400 response naming the invalid field
    return JSONResponse(
        status_code=400,
        content={
            "error": f"Invalid field: {field}",
            "message": error["msg"],
        },
    )


# =============================
# BASIC API ROUTES
# =============================

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
        "status": "healthy"
    }


# =============================
# TASK CRUD ROUTES
# =============================

# Define the data expected when creating a task
class TaskCreate(BaseModel):

    # Task title supplied by the client
    title: str

    # Task completion status
    done: bool = False


# Define the data expected when updating a task
class TaskUpdate(BaseModel):

    # Updated task title
    title: Optional[str] = None

    # Updated task completion status
    done: Optional[bool] = None


# Get all tasks
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


# Get one task by ID
@app.get("/tasks/{task_id}")
def get_task(task_id: int):

    # Open a database session
    with Session(engine) as session:

        # Find the task using its ID
        task = session.get(Task, task_id)

        # Return 404 if the task does not exist
        if not task:
            raise HTTPException(
                status_code=404,
                detail="Task not found",
            )

        # Return the requested task
        return task


# Create a new task
@app.post("/tasks")
def create_task(task_data: TaskCreate):

    # Open a database session
    with Session(engine) as session:

        # Create a new Task object
        task = Task(
            title=task_data.title,
            done=task_data.done,
        )

        # Add the task to the database
        session.add(task)

        # Save the task
        session.commit()

        # Refresh the object so it receives its database ID
        session.refresh(task)

        # Return the newly created task
        return task


# Update an existing task
@app.put("/tasks/{task_id}")
def update_task(
    task_id: int,
    task_data: TaskUpdate,
):

    # Open a database session
    with Session(engine) as session:

        # Find the task by ID
        task = session.get(Task, task_id)

        # Return 404 if the task does not exist
        if not task:
            raise HTTPException(
                status_code=404,
                detail="Task not found",
            )

        # Update the title if a new title was provided
        if task_data.title is not None:
            task.title = task_data.title

        # Update the done status if a new value was provided
        if task_data.done is not None:
            task.done = task_data.done

        # Save the updated task
        session.add(task)
        session.commit()

        # Refresh the task with the latest database values
        session.refresh(task)

        # Return the updated task
        return task


# Delete an existing task
@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):

    # Open a database session
    with Session(engine) as session:

        # Find the task by ID
        task = session.get(Task, task_id)

        # Return 404 if the task does not exist
        if not task:
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


# =============================
# LLM QUARANTINE LOGGING
# =============================

def quarantine_failure(
    property_text: str,
    raw_response: str,
    validation_error: str,
    repair_error: str,
):

    # Define where failed LLM responses will be stored
    log_path = "logs/quarantine.jsonl"

    # Create a structured record containing the failure information
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_version": "property-enrich-v1",
        "input": property_text,
        "raw_response": raw_response,
        "validation_error": validation_error,
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


# =============================
# PROPERTY ENRICHMENT ENDPOINT
# =============================

@app.post(
    "/enrich",
    response_model=PropertyEnrichment,
)
def enrich_property(
    property_input: PropertyInput,
):

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

        # Convert the LLM's text response into a Python dictionary
        parsed_response = parse_llm_response(
            raw_response
        )

        # Validate the dictionary against our Pydantic schema
        validated_response = validate_llm_response(
            parsed_response
        )

        # Return the validated response
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