FROM python:3.8.10-slim
RUN apt-get update && apt-get install -y build-essential cmake libgl1-mesa-glx ffmpeg libsm6 libxext6
WORKDIR /usr/src/app
RUN pip3 install --upgrade pip
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt
COPY . .
EXPOSE 8080/udp
EXPOSE 8080/tcp
CMD [ "python3", "main.py" ]
