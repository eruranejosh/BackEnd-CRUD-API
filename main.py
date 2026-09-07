#fast api to build the API and HTTP exception to out 404 if not found
from fastapi import FastAPI, HTTPException

#import sqlmodel to store data 
from sqlmodel import SQLModel, Field, Session, create_engine, select
from typing import Optional
import os
from src.llm.schema import PropertyInput, PropertyEnrichment
# Import Request so we can access the incoming HTTP request
from fastapi import FastAPI, HTTPException, Request

# Import the validation error handler
from fastapi.exceptions import RequestValidationError

# Import JSONResponse so we can return a custom 400 response
from fastapi.responses import JSONResponse
# Loads variables from the .env file
from dotenv import load_dotenv

# Load the .env file into the application environment
load_dotenv()


#tells fast api what to expect i.e: title will be a text
from pydantic import BaseModel

#builds the api
app = FastAPI()

#run the database initialization function on startup
@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    create_initial_tasks()

#this tells sqlmodel to create a database named class
class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    done: bool = False

#creates the database connection
#create database name and connection

sqlite_file_name = "tasks.db"

engine = create_engine(f"sqlite:///{sqlite_file_name}")  

#database initialization function

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

#funtion to open a database session
def create_initial_tasks():
    
    #open a dadatabase session
    with Session(engine) as session:
        
        #check if task already exists
        tasks = session.exec(select(Task)).all()

        #if empty do
        if not tasks:
            task1 = Task(title="Learn FastAPI", done=False)
            task2 = Task(title="Build CRUD API", done=False)
            task3 = Task(title="Push to GitHub", done=True)

            #put into the database session
            session.add(task1)
            session.add(task2)
            session.add(task3)

            #save these changes permanently
            session.commit()

#creates a new model : taskcreate to let fastapi know what to expect
class TaskCreate(BaseModel):
    title: str

#create another base model taskupdate to update tasks
class TaskUpdate(BaseModel):
    title: str
    done: bool 

@app.get("/", summary="API information")
def root():
    return {
        "name": "Task API",
        "version": "1.0",
        "endpoints": ["/tasks"]
    }

#health route
@app.get("/health", summary="health check")
def health():
    return {
        "status": "ok"
    }
#task route
@app.get("/tasks", summary="Get all tasks")
def get_tasks():
    with Session(engine) as session:
        tasks = session.exec(select(Task)).all()
        return tasks

#task body route

@app.get("/tasks/{task_id}", summary="Get one task")
def get_task(task_id: int):
    with Session(engine) as session:
        task = session.get(Task, task_id)

        if not task:
            raise HTTPException(
                status_code=404,
                detail={"error": f"Task {task_id} not found"}
            )

        return task

#create new tasks and raise an exception if task is an empty sting

@app.post("/tasks", status_code=201, summary="create a new task")
def create_task(task: TaskCreate):
    if task.title.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="Title cannot be empty"
        )

    with Session(engine) as session:
        new_task = Task(
            title=task.title,
            done=False
        )

        session.add(new_task)
        session.commit()
        session.refresh(new_task)

        return new_task

#update existing tasks
@app.put("/tasks/{task_id}", summary="Update a task")
def update_task(task_id: int, updated_task: TaskUpdate):
    if updated_task.title.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="Title cannot be empty"
        )

    with Session(engine) as session:
        task = session.get(Task, task_id)

        if not task:
            raise HTTPException(
                status_code=404,
                detail={"error": f"Task {task_id} not found"}
            )

        task.title = updated_task.title
        task.done = updated_task.done

        session.add(task)
        session.commit()
        session.refresh(task)

        return task

#delete individual task

@app.delete("/tasks/{task_id}", status_code=204, summary="Delete a task")
def delete_task(task_id: int):
    with Session(engine) as session:
        task = session.get(Task, task_id)

        if not task:
            raise HTTPException(
                status_code=404,
                detail={"error": f"Task {task_id} not found"}
            )

        session.delete(task)
        session.commit()

# Convert FastAPI's default validation error from 422 to the 400
# required by our assignment
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):

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

@app.post("/enrich", response_model=PropertyEnrichment)
def enrich_property(property_input: PropertyInput):
    if os.getenv("LLM_STUB") == "1":
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

    raise HTTPException(
        status_code=503,
        detail="LLM service is not connected yet"
    )