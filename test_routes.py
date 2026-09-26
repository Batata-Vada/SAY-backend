import requests

BASE_URL = "http://127.0.0.1:5000"


def print_response(response):

    print("Status:", response.status_code)

    try:
        print("Response:", response.json())
    except ValueError:
        print("Response:", response.text)

    print("-" * 50)


def login(name, password):

    print(f"LOGIN: {name}")

    response = requests.post(
        f"{BASE_URL}/login",
        json={
            "name": name,
            "password": password
        }
    )

    print_response(response)

    return response


# LOGIN
login_response = login(
    "master",
    "master123"
)

if login_response.status_code != 200:
    print("Login failed. Stopping.")
    exit()


# GET TOKEN
token = login_response.json()["token"]

print("SESSION TOKEN:")
print(token)
print()


# TEST /me
print("GETTING CURRENT USER")

response = requests.get(
    f"{BASE_URL}/me",
    headers={
        "Authorization": token
    }
)

print_response(response)