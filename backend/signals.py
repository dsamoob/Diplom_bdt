from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.dispatch import receiver, Signal
from django_rest_passwordreset.signals import reset_password_token_created

from backend.models import ConfirmEmailToken, User, CompanyDetails



new_user_registered = Signal()
order_status = Signal()
new_stock_list = Signal()
stock_list_update = Signal()
changes_message = Signal()
item_update = Signal()

@receiver(item_update)
def item_update_signal(receiver, subject, text, **kwargs):
    msg = EmailMultiAlternatives(
        # title:
        f"{subject}",
        # message:
        f'{text}',
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [receiver]
    )

@receiver(changes_message)
def changes_message_signal(receiver, order, text, **kwargs):
    msg = EmailMultiAlternatives(
        # title:
        f"Обновление статуса заказа # {order}",
        # message:
        f'{text}',
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [receiver]
    )
    msg.send()



@receiver(order_status)
def order_status_signal(receiver, order, text, **kwargs):
    """
    отправяем письмо при изменении статуса заказа
    """
    # send an e-mail to the user

    msg = EmailMultiAlternatives(
        # title:
        f"Обновление статуса заказа # {order}",
        # message:
        f'{text}',
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [receiver.email]
    )
    msg.send()


@receiver(stock_list_update)
def stock_list_update_signal(obj, request_data, user=None, **kwargs):

    msg = EmailMultiAlternatives(
        f"Сток лист от {obj.company.name} обновился",

        f'{request_data}',
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [user.email]
    )
    msg.send()
@receiver(new_stock_list)
def new_stock_list_signal(nsl,  **kwargs):
    """
    Отправляем письмо пользователю с типом staff
    """
    # send an e-mail to the user-staff
    user = User.objects.get(type='staff')
    msg = EmailMultiAlternatives(
        f"новый сток лист от {nsl.company.name}",

        f"id: {nsl.id=}\n"
        f"shipment_dat: {nsl.shipment_date}\n"
        f"orders_till_date: {nsl.orders_till_date}\n"
        f"stock_type: {nsl.stock_type.name}\n"
        f"bags_quantity: {nsl.bags_quantity}\n"
        f"box_weight: {nsl.box_weight}\n"
        f"currency_type: {nsl.currency_type}\n"
        f"transport_type: {nsl.transport_type}\n",
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [user.email]
    )
    msg.send()

@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, **kwargs):
    """
    Отправляем письмо с токеном для сброса пароля
    When a token is created, an e-mail needs to be sent to the user
    :param sender: View Class that sent the signal
    :param instance: View Instance that sent the signal
    :param reset_password_token: Token Model Object
    :param kwargs:
    :return:
    """
    # send an e-mail to the user

    msg = EmailMultiAlternatives(
        # title:
        f"Password Reset Token for {reset_password_token.user}",
        # message:
        reset_password_token.key,
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [reset_password_token.user.email]
    )
    msg.send()


@receiver(new_user_registered)
def new_user_registered_signal(user_id, **kwargs):
    """
    отправляем письмо с подтрердждением почты
    """
    # send an e-mail to the user
    token, _ = ConfirmEmailToken.objects.get_or_create(user_id=user_id)

    msg = EmailMultiAlternatives(
        # title:
        f"Password Reset Token for {token.user.email}",
        # message:
        token.key,
        # from:
        settings.EMAIL_HOST_USER,
        # to:
        [token.user.email]
    )
    msg.send()





