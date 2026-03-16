from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok", "message": "API работает"}

@app.get("/test")
def test():
    return {"data": "тест"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)