from django.core.mail import send_mail

def send(cnee: str, sndr: str, text: str, sbj: str):
    send_mail(sbj,
              text,
              sndr,
              [cnee],
              fail_silently=False)