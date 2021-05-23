FROM python:3.8.10-slim
RUN apt-get update && apt-get install -y build-essential cmake
WORKDIR /usr/src/app
COPY . .
RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt
CMD [ "python3", "main.py" ]
