"""패키지 설치 확인 전용. DB/API에 접속하거나 모델을 내려받지 않습니다."""

from importlib import import_module
from importlib.metadata import version
import os
import tempfile

# Ultralytics의 사용자 설정은 저장소 바깥 임시 경로에 둡니다.
os.environ.setdefault("YOLO_CONFIG_DIR", tempfile.gettempdir() + "/octv-yolo-check")

PACKAGES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pydantic": "pydantic",
    "pydantic-settings": "pydantic_settings",
    "python-dotenv": "dotenv",
    "psycopg": "psycopg",
    "httpx": "httpx",
    "PyJWT": "jwt",
    "pwdlib": "pwdlib",
    "email-validator": "email_validator",
    "torch": "torch",
    "torchvision": "torchvision",
    "ultralytics": "ultralytics",
    "opencv-python": "cv2",
    "numpy": "numpy",
    "langgraph": "langgraph.graph",
    "fastmcp": "fastmcp",
    "langchain-openai": "langchain_openai",
}

for package, module in PACKAGES.items():
    import_module(module)
    print(f"{package}: {version(package)}")

# Torch와 TorchVision의 native 연산이 서로 호환되는지 확인합니다.
import torch
from torchvision.ops import nms
import cv2
import numpy as np
from pwdlib import PasswordHash
from fastmcp import FastMCP
from langgraph.graph import StateGraph
from langchain_openai import ChatOpenAI
from ultralytics import YOLO

boxes = torch.tensor([[0.0, 0.0, 2.0, 2.0], [0.0, 0.0, 2.0, 2.0]])
scores = torch.tensor([0.9, 0.5])
assert nms(boxes, scores, 0.5).tolist() == [0]
assert cv2.cvtColor(np.zeros((2, 2, 3), dtype=np.uint8), cv2.COLOR_BGR2GRAY).shape == (
    2,
    2,
)
hasher = PasswordHash.recommended()
assert hasher.verify("install-check-only", hasher.hash("install-check-only"))
print("Python 개발 환경 확인 완료 (외부 연동·모델 추론은 실행하지 않음)")
