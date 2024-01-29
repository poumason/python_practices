from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI
import uvicorn
import logging
import os
from urllib.parse import urlencode
from fastapi import FastAPI, Response, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import math
import random
import base64
import requests

# https://github.com/duranbe/spotify-fastapi-sample/blob/main/src/main.py

print(os.path.join(os.getcwd(),"webapi","templates"))
app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(os.getcwd(),"webapi","templates"))
instrumentator = Instrumentator().instrument(app)

STATE_KEY = "spotify_auth_state"
CLIENT_ID = os.environ["SP_CLIENT_ID"]
CLIENT_SECRET = os.environ["SP_CLIENT_SECRET"]
URI = os.environ["SP_URI"]
REDIRECT_URI = URI + "/callback"

@app.on_event("startup")
async def _startup():
    instrumentator.expose(app)

# @app.get("/")
# def read_root():
#     logging.info('root path')
#     return {"Hello": "World"}


# @app.get("/items/{item_id}")
# def read_item(item_id: int):
#     logging.info(f'item_id: {item_id}')
#     return {"item_id": item_id}

def generate_random_string(string_length):
    possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    text = "".join(
        [
            possible[math.floor(random.random() * len(possible))]
            for i in range(string_length)
        ]
    )

    return text

@app.get("/login")
def read_root(response: Response):
    state = generate_random_string(20)

    scope = "user-read-private user-read-email user-read-recently-played user-top-read"

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "scope": scope,
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    response = RedirectResponse(
        url="https://accounts.spotify.com/authorize?" + urlencode(params)
    )
    response.set_cookie(key=STATE_KEY, value=state)
    return response

@app.get("/callback")
def callback(request: Request, response: Response):

    code = request.query_params["code"]
    state = request.query_params["state"]
    stored_state = request.cookies.get(STATE_KEY)

    if state == None or state != stored_state:
        raise HTTPException(status_code=400, detail="State mismatch")
    else:

        response.delete_cookie(STATE_KEY, path="/", domain=None)

        url = "https://accounts.spotify.com/api/token"
        request_string = CLIENT_ID + ":" + CLIENT_SECRET
        encoded_bytes = base64.b64encode(request_string.encode("utf-8"))
        encoded_string = str(encoded_bytes, "utf-8")
        header = {"Authorization": "Basic " + encoded_string}

        form_data = {
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        api_response = requests.post(url, data=form_data, headers=header)

        if api_response.status_code == 200:
            data = api_response.json()
            access_token = data["access_token"]
            refresh_token = data["refresh_token"]

            response = RedirectResponse(url=URI)
            response.set_cookie(key="accessToken", value=access_token)
            response.set_cookie(key="refreshToken", value=refresh_token)

        return response


@app.get("/", response_class=HTMLResponse)
def main(request: Request):

    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/refresh_token")
def refresh_token(request: Request):

    refresh_token = request.query_params["refresh_token"]
    request_string = CLIENT_ID + ":" + CLIENT_SECRET
    encoded_bytes = base64.b64encode(request_string.encode("utf-8"))
    encoded_string = str(encoded_bytes, "utf-8")
    header = {"Authorization": "Basic " + encoded_string}

    form_data = {"grant_type": "refresh_token", "refresh_token": refresh_token}

    url = "https://accounts.spotify.com/api/token"

    response = requests.post(url, data=form_data, headers=header)
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Error with refresh token")
    else:
        data = response.json()
        access_token = data["access_token"]

        return {"access_token": access_token}


if __name__ == "__main__":
    uvicorn.run("main:app", port=5000, log_level="info")
                # , host="0.0.0.0")