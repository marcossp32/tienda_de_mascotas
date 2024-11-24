FROM python:3.9

WORKDIR /app

COPY create_tables.py /app/
COPY insert-data.py /app/

COPY requirements.txt /app/
RUN pip install -r requirements.txt

CMD ["python", "create_tables.py"]
