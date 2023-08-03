from Diplom_bdt.celery import app

from .service import send


@app.task
def send_email(cnee: str, sndr: str, text: str, sbj: str):
    send(cnee, sndr, text, sbj)
