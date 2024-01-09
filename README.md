# bookstore_cart
Microservice for product cart in Bookstore. Microservice is a part of the Cloud-native application.

### Installation
Since the microservice is built using FastAPI you need python and pip installed on your machine.
1. Clone the repository
2. Move to the project's root folder
3. (*OPTIONAL*) Create virtual environment `python3 -m venv venv`
4. (*OPTIONAL*) Activate virtual environment `source venv/bin/activate`
5. Install required packages `pip install -r requirements.txt`

### Starting the server
To start the microservice you simply run: `uvicorn main:app --reload`. The server is listening on port 8000 by default. The API documentation is located on `/openapi`.
