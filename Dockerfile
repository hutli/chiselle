FROM python:3.14
WORKDIR /wd

COPY ./requirements.txt /wd/
RUN pip install -r /wd/requirements.txt

COPY ./mypy.ini /wd/
COPY ./app /wd/app

RUN mypy app --config-file /wd/mypy.ini

CMD ["python", "-m", "app.app"]