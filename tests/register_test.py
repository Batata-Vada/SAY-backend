
import requests

url = "http://127.0.0.1:5001/register"

data = {
    "name": "sid_test",
    "email": "sid.test@example.com",
    "password": "ExamplePassword123!"
}

response = requests.post(url, json=data, timeout=15)

print("Status:", response.status_code)
print("Response:", response.json())