FROM alpine:3.7

RUN apk update && \
    apk add py-pip

ADD requirements.txt /
RUN pip install -r /requirements.txt

ADD cli.py /

ENTRYPOINT ["python", "/cli.py"]
