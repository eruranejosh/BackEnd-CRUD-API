#fast api to build the API and HTTP exception to out 404 if not found
from fastapi import FastAPI, HTTPException

#tells fast api what to expect i.e: title will be a text
from pydantic import BaseModel

#builds the api
app = FastAPI()

#the task route body
tasks = [
    {
        "id": 1,
        "title": "Learn FastAPI",
        "done": False
    },
    {
        "id": 2,
        "title": "Build CRUD API",
        "done": False
    },
    {
        "id": 3,
        "title": "Push to GitHub",
        "done": True
    }
]

#creates a new model : taskcreate to let fastapi know what to expect
class TaskCreate(BaseModel):
    title: str

#create another base model taskupdate to update tasks
class TaskUpdate(BaseModel):
    title: str
    done: bool 

@app.get("/")
def root():
    return {
        "name": "Task API",
        "version": "1.0",
        "endpoints": ["/tasks"]
    }

#health route
@app.get("/health")
def health():
    return {
        "status": "ok"
    }
#task route
@app.get("/tasks")
def get_tasks():
    return tasks

#task body route

@app.get("/tasks/{id}")
def get_task(id: int):
    for task in tasks:
        if task["id"] == id:
            return task

    raise HTTPException(
        status_code=404,
        detail=f"Task {id} not found"
    )

#create new tasks and raise an exception if task is an empty sting

@app.post("/tasks", status_code=201)
def create_task(task: TaskCreate):
    if task.title.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="Title cannot be empty"
        )

    new_task = {
        "id": len(tasks) + 1,
        "title": task.title,
        "done": False
    }

    tasks.append(new_task)

    return new_task

#update existing tasks
@app.put("/tasks/{id}")
def update_task(id: int, updated_task: TaskUpdate):
    for task in tasks:
        if task["id"] == id:
            task["title"] = updated_task.title
            task["done"] = updated_task.done
            return task

    raise HTTPException(
        status_code=404,
        detail=f"Task {id} not found"
    )

#delete individual task

@app.delete("/tasks/{id}", status_code=204)
def delete_task(id: int):
    for task in tasks:
        if task["id"] == id:
            tasks.remove(task)
            return

    raise HTTPException(
        status_code=404,
        detail=f"Task {id} not found"
    )
