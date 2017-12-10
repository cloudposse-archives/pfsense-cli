FROM alpine:3.7

RUN apk update && \
    apk add py-pip

ADD cli.py /
ADD requirements.txt /
RUN pip install -r /requirements.txt


ENTRYPOINT ["python", "/cli.py"]
