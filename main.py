import os
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
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
import requests

class Config:
    db_url: str = None
    app_name: str = "bookstore_cart"
    version: str = "v1"
    catalog_host: str = 'localhost'
    catalog_port: str = '8000'
    # Read from .env file
    try:
        db_url = dotenv_values('.env')['DB_URL']
        app_name = dotenv_values('.env')['APP_NAME']
    except Exception as e:
        print('No .env file with DB_URL and APP_NAME found...')
    # Read from ENV
    db_url = os.getenv('DB_URL', default=db_url)
    app_name = os.getenv('APP_NAME', default=app_name)
    catalog_host = os.getenv('BOOKSTORE_CATALOG_SERVICE_HOST', default=catalog_host)
    catalog_port = os.getenv('BOOKSTORE_CATALOG_SERVICE_PORT', default=catalog_port)

    catalog_url = f'http://{catalog_host}:{catalog_port}'
    broken: bool = False

logger = logging.getLogger('uvicorn')

CONFIG = Config()
app = FastAPI(title=APP_METADATA['title'], 
              summary=APP_METADATA['summary'], 
              description=APP_METADATA['description'], 
              contact=APP_METADATA['contact'],
              openapi_tags=APP_METADATA['tags_metadata'],
              root_path="/bookstore-cart" if CONFIG.catalog_host != 'localhost' else "",
              docs_url='/openapi')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    idem = uuid.uuid4()
    logger.info(f"method={str.upper(request.method)} rid={idem} app={CONFIG.app_name} version={CONFIG.version} START_REQUEST path={request.url.path}")
    start_time = time.time()
    
    # add request id to the request
    request.state.rid = str(idem)
    response = await call_next(request)
    
    process_time = (time.time() - start_time) * 1000
    formatted_process_time = '{0:.2f}'.format(process_time)
    logger.info(f"method={str.upper(request.method)} rid={idem} app={CONFIG.app_name} version={CONFIG.version} END_REQUEST completed_in={formatted_process_time}ms status_code={response.status_code}")
    
    return response

class NewItem(BaseModel):
    book_id: int
    quantity: int

class NewOrder(BaseModel):
    name: str
    surname: str
    post_code: int
    address: str
    city: str

class Cart(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int
    user_id: int
    quantity: int

class Orders(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int
    name: str
    surname: str
    post_code: int
    address: str
    city: str

def get_book(id: int, rid: str):
    url = f'{CONFIG.catalog_url}/books/{id}'
    book = requests.get(url=url, headers={'rid': rid}).json()
    return book

@app.on_event("startup")
@repeat_every(seconds=5)
def reload_config():
    global CONFIG
    logger.info(f"app={CONFIG.app_name} version={CONFIG.version} | Reloading config")

    db_url = None
    app_name = None
    catalog_host: str = None
    catalog_port: str = None
    # Read from .env file
    try:
        db_url = dotenv_values('.env')['DB_URL']
        app_name = dotenv_values('.env')['APP_NAME']
    except Exception as e:
        pass
    # Read from ENV
    db_url = os.getenv('DB_URL', default=db_url)
    app_name = os.getenv('APP_NAME', default=app_name)
    catalog_host = os.getenv('BOOKSTORE_CATALOG_SERVICE_HOST', default=catalog_host)
    catalog_port = os.getenv('BOOKSTORE_CATALOG_SERVICE_PORT', default=catalog_port)
    catalog_url = f'http://{catalog_host}:{catalog_port}'

    if db_url != None:
        CONFIG.db_url = db_url
    else:
        raise KeyError('No DB URL specified in ENV...')
    
    if app_name != None:
        CONFIG.app_name = app_name
    else:
        raise KeyError('No APP NAME specified in ENV...')

    if catalog_port != None and catalog_host != None:
        CONFIG.catalog_host = catalog_host
        CONFIG.catalog_port = catalog_port
        CONFIG.catalog_url = catalog_url

if CONFIG.db_url == None:
    raise KeyError('No DB URL specified in ENV...')

if CONFIG.catalog_url == None:
    raise KeyError('No BOOKSTORE CATALOG URL specified in ENV...')

engine = create_engine(CONFIG.db_url)

@app.get("/")
def read_root():
    return {"Hello": "World", "app_name": CONFIG.app_name}

@app.get("/cart", tags=['cart'])
def get_all_shopping_carts(request: Request, response: Response):
    rid = request.state.rid
    with Session(engine) as session:
        carts = session.exec(select(Cart)).all()
        res = []
        for cart in carts:
            book = get_book(cart.book_id, rid)
            # book = session.exec(select(Books).where(Books.id == cart.book_id)).one()
            res.append({'id': cart.id, 'user_id': cart.user_id, 'quantity': cart.quantity, 'book': book})
        response.status_code = status.HTTP_200_OK
        return res


@app.get("/cart/{id}", tags=['cart'])
def get_shopping_cart(request: Request, id: int, response: Response):
    rid = request.state.rid
    with Session(engine) as session:
        cart = session.exec(select(Cart).where(Cart.user_id == id)).all()
        res = []
        price = 0
        for c in cart:
            book = get_book(c.book_id, rid)
            # book = session.exec(select(Books).where(Books.id == c.book_id)).one()
            res.append({'id': c.id, 'user_id': c.user_id, 'quantity': c.quantity, 'book': book, 'price': c.quantity * book['price']})
            price += c.quantity * book['price']
        response.status_code = status.HTTP_200_OK
        return {'cart': res, 'price': price}

@app.post('/cart/{user_id}', tags=['cart'])
def add_new_item_to_shopping_cart(user_id: int, newItem: NewItem, response: Response):
    print(newItem)
    with Session(engine) as session:
        cart = session.exec(select(Cart).where(Cart.user_id == user_id).where(Cart.book_id == newItem.book_id)).one_or_none()
        print(cart)
        if cart != None:
            cart.quantity += newItem.quantity
        else:
            cart = Cart(user_id=user_id, book_id=newItem.book_id, quantity=newItem.quantity)
        print(cart)
        session.add(cart)
        session.commit()
        response.status_code = status.HTTP_201_CREATED
        return cart
    
@app.delete('/cart/{user_id}/{book_id}', tags=['cart'])
def delete_item_from_shopping_cart(user_id: int, book_id: int, response: Response):
    with Session(engine) as session:
        cart = session.exec(select(Cart).where(Cart.user_id == user_id).where(Cart.book_id == book_id)).one_or_none()
        if cart == None:
            response.status_code = status.HTTP_200_OK
        else:
            cart.quantity = max(0, cart.quantity - 1)
        
        if cart.quantity == 0:
            session.delete(cart)
        else:
            session.add(cart)
        session.commit()
        response.status_code = status.HTTP_200_OK
        return cart

@app.get('/orders', tags=['orders'])
def get_all_orders(request: Request, response: Response):
    rid = request.state.rid
    with Session(engine) as session:
        res = []
        orders = session.exec(select(Orders)).all()
        for order in orders:
            user = order.user_id
            cart = session.exec(select(Cart).where(Cart.user_id == user)).all()
            user_cart = []
            price = 0
            for c in cart:
                book = get_book(c.book_id, rid)
                user_cart.append({'id': c.id, 'user_id': c.user_id, 'quantity': c.quantity, 'book': book, 'price': c.quantity * book['price']})
                price += c.quantity * book['price']
            res.append({
                'user_id': user,
                 'id': order.id,
                 'name': order.name,
                 'surname': order.surname,
                 'post_code': order.post_code,
                 'address': order.address,
                 'city': order.city,
                 'price': price,
                 'cart': user_cart
            })
        response.status_code = status.HTTP_200_OK
        return res


@app.get('/orders/{user_id}', tags=['orders'])
def get_user_order(user_id: int, request: Request, response: Response):
    rid = request.state.rid
    with Session(engine) as session:
        res = []
        orders = session.exec(select(Orders).where(Orders.user_id == user_id)).all()
        for order in orders:
            user = order.user_id
            cart = session.exec(select(Cart).where(Cart.user_id == user)).all()
            user_cart = []
            price = 0
            for c in cart:
                book = get_book(c.book_id, rid)
                user_cart.append({'id': c.id, 'user_id': c.user_id, 'quantity': c.quantity, 'book': book, 'price': c.quantity * book['price']})
                price += c.quantity * book['price']
            res.append({
                'user_id': user,
                 'id': order.id,
                 'name': order.name,
                 'surname': order.surname,
                 'post_code': order.post_code,
                 'address': order.address,
                 'city': order.city,
                 'price': price,
                 'cart': user_cart
            })
        response.status_code = status.HTTP_200_OK
        return res
    
@app.post('/orders/{user_id}', tags=['orders'])
def create_new_order(request: Request, user_id: int, newOrder: NewOrder, response: Response):
    with Session(engine) as session:
        carts = session.exec(select(Cart).where(Cart.user_id == user_id)).all()
        if (len(carts) == 0 or carts is None):
            return
        order = Orders(user_id=user_id, name=newOrder.name, surname=newOrder.surname, post_code=newOrder.post_code, address=newOrder.address, city=newOrder.city)
        session.add(order)
        session.commit()
        response.status_code = status.HTTP_201_CREATED
        return order
    
@app.delete('/orders/{order_id}', tags=['orders'])
def delete_order(order_id: int, response: Response):
    with Session(engine) as session:
        order = session.exec(select(Orders).where(Orders.id == order_id)).one_or_none()
        if order is None:
            response.status_code = status.HTTP_200_OK
            return None
        
        session.delete(order)
        session.commit()
        response.status_code = status.HTTP_200_OK
        return None
    
@app.put('/orders/{order_id}', tags=['orders'])
def update_order_info(order_id: int, updatedOrder: NewOrder, response: Response):
    with Session(engine) as session:
        order = session.exec(select(Orders).where(Orders.id == order_id)).one_or_none()
        if order is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return None
        order.name = updatedOrder.name
        order.surname = updatedOrder.surname
        order.post_code = updatedOrder.post_code
        order.address = updatedOrder.address
        order.city = updatedOrder.city

        session.add(order)
        session.commit()
        response.status_code = status.HTTP_201_CREATED
        return order


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