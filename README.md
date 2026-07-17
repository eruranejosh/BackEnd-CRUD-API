BackEnd CRUD API

A simple RESTful CRUD API built with FastAPI that manages a to-do list in memory. The API allows users to create, read, update, and delete tasks, and includes interactive API documentation using Swagger UI.

Features

* Create new tasks
* View all tasks
* View a single task by ID
* Update existing tasks
* Delete tasks
* In-memory data storage (no database)
* Automatic interactive API documentation with Swagger UI

Technologies Used

* Python 3
* FastAPI
* Uvicorn
* Pydantic
* Swagger UI

Installation

1. Clone the repository

git clone https://github.com/eruranejosh/BackEnd-CRUD-API.git
cd BackEnd-CRUD-API

2. Create a virtual environment

python3 -m venv backendapi

3. Activate the virtual environment

macOS/Linux

source backendapi/bin/activate

Windows

backendapi\Scripts\activate

4. Install the required packages

pip install fastapi uvicorn

5. Run the application

uvicorn main:app --reload

The server will start at:

http://127.0.0.1:8000

Swagger UI

Interactive API documentation is available at:

http://127.0.0.1:8000/docs

Swagger UI allows you to test every endpoint directly from your browser using the Try it out button.

API Endpoints

Method	Endpoint	Description
GET	/	Returns API information
GET	/health	Health check endpoint
GET	/tasks	Retrieve all tasks
GET	/tasks/{id}	Retrieve a task by its ID
POST	/tasks	Create a new task
PUT	/tasks/{id}	Update an existing task
DELETE	/tasks/{id}	Delete a task

Example cURL Request

Create a new task:

curl -i -X POST http://127.0.0.1:8000/tasks \
-H "Content-Type: application/json" \
-d '{"title":"Buy milk"}'

Example response:

HTTP/1.1 201 Created
{
  "id": 4,
  "title": "Buy milk",
  "done": false
}

Project Structure

BackEnd-CRUD-API/
│── main.py
│── requirements.txt
│── README.md
│── .gitignore

Notes

* This project stores data in memory using a Python list.
* Restarting the server resets the task list to the initial sample data.
* This behavior is intentional for this assignment, as no database is used.

Author

Joshua Erurane
