from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.contrib.auth.models import AbstractUser
from django_rest_passwordreset.tokens import get_token_generator


STOCK_TYPES = (
    ('freshwater', 'Пресноводные'),
    ('marine', 'морские'),
    ('plants', 'растения')
)

USER_TYPE_CHOICES = (
    ('shpr', 'Магазин'),
    ('cnee', 'Покупатель'),
    ('staff', 'Работник')
)

POL = (
    ('SVO', 'ШРМ'),
    ('DME', 'ДМД'),
    ('VKO', 'ВНК'),
)

SHIPMENT_STATUS = (
    ('Confirmed', 'Принято'),
    ('Shipped', 'Отправлено')
)

class UserManager(BaseUserManager):
    """
    Миксин для управления пользователями
    """
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given username, email, and password.
        """
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    REQUIRED_FIELDS = []
    objects = UserManager()
    USERNAME_FIELD = 'email'
    type = models.CharField(verbose_name='Тип пользователя', choices=USER_TYPE_CHOICES, max_length=5, default='cnee')
    email = models.EmailField(('email address'), unique=True)
    phone = models.CharField(max_length=16, unique=True)


class ConfirmEmailToken(models.Model):
    class Meta:
        verbose_name = 'Токен подтверждения Email'
        verbose_name_plural = 'Токены подтверждения Email'

    @staticmethod
    def generate_key():
        """ generates a pseudo random code using os.urandom and binascii.hexlify """
        return get_token_generator().generate_token()

    user = models.ForeignKey(
        User,
        related_name='confirm_email_tokens',
        on_delete=models.CASCADE,
        verbose_name=("The User which is associated to this password reset token")
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=("When was this token generated")
    )

    # Key field, though it is not the primary key of the model
    key = models.CharField(
        ("Key"),
        max_length=64,
        db_index=True,
        unique=True
    )

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super(ConfirmEmailToken, self).save(*args, **kwargs)

    def __str__(self):
        return "Password reset token for user {user}".format(user=self.user)



class State(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Страна')

    def __str__(self):
        return self.name

class City(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Город')
    state_id = models.ForeignKey(State, on_delete=models.CASCADE, related_name='cities')
    # state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='cities')

    def __str__(self):
        return self.name


class CompanyDetails(models.Model):
    city_id = models.ForeignKey(City, on_delete=models.CASCADE)
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=150, verbose_name='Название компании')
    street = models.CharField(max_length=150, verbose_name='Улица')
    bld = models.CharField(max_length=30, verbose_name='Строение')
    bank_details = models.CharField(max_length=200, verbose_name='Банковские детали')

    def __str__(self):
        return f'{self.name}, {self.street}, {self.bld}, {self.bank_details}'


class ShipTo(models.Model):
    city_id = models.ForeignKey(City, on_delete=models.CASCADE)
    company_details_id = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE)
    street = models.CharField(max_length=150, verbose_name='Улица')
    bld = models.CharField(max_length=50, verbose_name='Строение')
    contact_person = models.CharField(max_length=150, verbose_name='Контактное лицо')
    phone = models.CharField(max_length=20, verbose_name='Телефон контактного лица')



class StockType(models.Model):
    name = models.CharField(max_length=15, choices=STOCK_TYPES, default='freshwater')

    def __str__(self):
        return self.name


class StockList(models.Model):
    company_details_id = models.ForeignKey(User, on_delete=models.CASCADE)
    orders_till_date = models.DateTimeField(verbose_name='Дата окончания приема зказаов')
    shipment_date = models.DateTimeField(verbose_name='Дата поставки')
    stock_type_id = models.ForeignKey(StockType, on_delete=models.CASCADE)
    bags_quantity = models.IntegerField(default=4, verbose_name='Кол-во пакетов в коробке')
    currency_rate = models.DecimalField(max_digits=4, decimal_places=2, verbose_name='Курс доллара')
    status = models.BooleanField(default=True)
    box_weight = models.DecimalField(max_digits=4, decimal_places=2, verbose_name='Вес одной коробки')


class Item(models.Model):
    company_details_id = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE)
    code = models.CharField(max_length=10)
    english_name = models.CharField(max_length=100, verbose_name='Местное название')
    scientific_name = models.CharField(max_length=100, verbose_name='Научное название')
    russian_name = models.CharField(max_length=100, verbose_name='Русское название')
    size = models.CharField(max_length=15, verbose_name='Размер', default='All size')

    def __str__(self):
        return f'{self.code} {self.english_name} {self.scientific_name} {self.russian_name} {self.size}'


class StockListItem(models.Model):
    item_id = models.ForeignKey(Item, on_delete=models.CASCADE)
    stock_list_id = models.ForeignKey(StockList, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=7, decimal_places=2, verbose_name='Цена')
    quantity_bag = models.IntegerField(verbose_name='Кол-во в пакете')
    ordered = models.IntegerField(verbose_name='Заказано')
    limit = models.IntegerField(verbose_name='Кол-во в наличии')
    english_name = models.CharField(max_length=100, verbose_name='Местное название', blank=True, default=None)
    scientific_name = models.CharField(max_length=100, verbose_name='Научное название', blank=True, default=None)
    russian_name = models.CharField(max_length=100, verbose_name='Русское название', blank=True, default=None)
    size = models.CharField(max_length=15, verbose_name='Размер', blank=True, default=None)


class FreightRates(models.Model):
    POL = models.CharField(max_length=5, choices=POL, verbose_name='Аэропорт отправления')
    city_id = models.ForeignKey(City, on_delete=models.CASCADE)
    minimal_weight = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Минимальный вес')
    price = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Цена за 1 кг')


class Order(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    total_quantity = models.DecimalField(max_digits=8, decimal_places=0, verbose_name='Кол-во заказанных шт.', blank=True, default=0)
    total_amoun = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Сумма заказа', blank=True, default=0)
    date = models.DateTimeField(auto_now_add=True, verbose_name='Дата заказа')
    box_quantity = models.DecimalField(max_digits=2, decimal_places=0, verbose_name='Кол-во заказанных коробок', blank=True, default=0)


class Delivery(models.Model):
    ship_to_id = models.ForeignKey(ShipTo, on_delete=models.CASCADE)
    shipment_status = models.CharField(max_length=20, choices=SHIPMENT_STATUS, default='Confirmed')
    shipment_date = models.DateTimeField(blank=True)


class OrderDelivery(models.Model):
    order_id = models.ForeignKey(Order, on_delete=models.CASCADE)
    delivery_id = models.ForeignKey(Delivery, on_delete=models.CASCADE)
