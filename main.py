import os
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Response, status
from sqlmodel import Field, Session, SQLModel, create_engine, select
from fastapi_utils.tasks import repeat_every
import os
from pydantic import BaseModel
from dotenv import dotenv_values
import logging
import time
import uuid
from enum import Enum
from app_metadata import APP_METADATA

class Config:
    db_url: str = None
    app_name: str = "bookstore_cart"
    version: str = "v1"
    # Read from .env file
    try:
        db_url = dotenv_values('.env')['DB_URL']
        app_name = dotenv_values('.env')['APP_NAME']
    except Exception as e:
        print('No .env file with DB_URL and APP_NAME found...')
    # Read from ENV
    db_url = os.getenv('DB_URL', default=db_url)
    app_name = os.getenv('APP_NAME', default=app_name)

    broken: bool = False

logger = logging.getLogger('uvicorn')

CONFIG = Config()
app = FastAPI(title=APP_METADATA['title'], 
              summary=APP_METADATA['summary'], 
              description=APP_METADATA['description'], 
              contact=APP_METADATA['contact'],
              openapi_tags=APP_METADATA['tags_metadata'],
              root_path="/bookstore-cart")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    idem = uuid.uuid4()
    logger.info(f"method={str.upper(request.method)} rid={idem} app={CONFIG.app_name} version={CONFIG.version} START_REQUEST path={request.url.path}")
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = (time.time() - start_time) * 1000
    formatted_process_time = '{0:.2f}'.format(process_time)
    logger.info(f"method={str.upper(request.method)} rid={idem} app={CONFIG.app_name} version={CONFIG.version} END_REQUEST completed_in={formatted_process_time}ms status_code={response.status_code}")
    
    return response

class NewItem(BaseModel):
    book_id: int
    quantity: int


class Cart(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int
    user_id: int
    quantity: int

class Books(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    author: str
    genre: str
    description: str
    price: int
    stock_quantity: int

@app.on_event("startup")
@repeat_every(seconds=5)
def reload_config():
    global CONFIG
    logger.info(f"app={CONFIG.app_name} version={CONFIG.version} | Reloading config")

    db_url = None
    app_name = None
    # Read from .env file
    try:
        db_url = dotenv_values('.env')['DB_URL']
        app_name = dotenv_values('.env')['APP_NAME']
    except Exception as e:
        pass
    # Read from ENV
    db_url = os.getenv('DB_URL', default=db_url)
    app_name = os.getenv('APP_NAME', default=app_name)

    if db_url != None and app_name != None:
        CONFIG.db_url = db_url
        CONFIG.app_name = app_name
    else:
        raise KeyError('No DB URL or APP NAME specified in ENV...')


if CONFIG.db_url == None:
    raise KeyError('No DB URL specified in ENV...')

engine = create_engine(CONFIG.db_url, echo=True)

@app.get("/")
def read_root():
    return {"Hello": "World", "app_name": CONFIG.app_name}

@app.get("/cart", tags=['cart'])
def get_all_shopping_carts(response: Response):
    with Session(engine) as session:
        carts = session.exec(select(Cart)).all()
        res = []
        for cart in carts:
            book = session.exec(select(Books).where(Books.id == cart.book_id)).one()
            res.append({'id': cart.id, 'user_id': cart.user_id, 'quantity': cart.quantity, 'book': book})
        response.status_code = status.HTTP_200_OK
        return res


@app.get("/cart/{id}", tags=['cart'])
def get_shopping_cart(id: int, response: Response):
    with Session(engine) as session:
        cart = session.exec(select(Cart).where(Cart.user_id == id)).all()
        res = []
        for c in cart:
            book = session.exec(select(Books).where(Books.id == c.book_id)).one()
            res.append({'id': c.id, 'user_id': c.user_id, 'quantity': c.quantity, 'book': book})
        response.status_code = status.HTTP_200_OK
        return res

@app.post('/cart/{user_id}', tags=['cart'])
def add_new_item_to_shopping_cart(user_id: int, newItem: NewItem, response: Response):
    with Session(engine) as session:
        cart = Cart(user_id=user_id, book_id=newItem.book_id, quantity=newItem.quantity)
        session.add(cart)
        session.commit()
        response.status_code = status.HTTP_200_OK
        return cart

@app.get("/health/live", tags=['healthchecks'])
async def get_health_live(response: Response):
        healthy = True
        try:
            session = Session(engine)
            session.close()
            healthy = True
        except Exception as e:
            print(e)
            healthy = False

        if CONFIG.broken:
            healthy = False
        
        if healthy:
            response.status_code = status.HTTP_200_OK
            return {"State": "UP"}
        else:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"State": "DOWN"}

@app.get("/health/ready", tags=['healthchecks'])
async def get_health_ready(response: Response):
        healthy = True

        if CONFIG.broken:
            healthy = False
        
        if healthy:
            response.status_code = status.HTTP_200_OK
            return {"State": "UP"}
        else:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"State": "DOWN"}
        
@app.post("/broken", tags=['healthchecks'])
def set_broken():
    CONFIG.broken = True
    return Response(status_code=201)