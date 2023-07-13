from abc import ABC
from backend.models import User, CompanyDetails, State, \
    City, ShipAddresses, FreightRates, StockType, StockList, Item, StockListItem, Order, OrderedItems, FreightRatesSet
from rest_framework import serializers
from datetime import datetime as dt
from datetime import date
from datetime import timedelta as td
from django.db.models import Sum
from rest_framework.serializers import ValidationError as VE
from django.core.exceptions import ValidationError


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ('id', 'name')


class FreightRatesSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField('get_city_name')

    def get_city_name(self, obj):
        return obj.city.name

    class Meta:
        model = FreightRates
        fields = '__all__'


class StateSerializer(serializers.ModelSerializer):
    cities = CitySerializer(many=True)

    class Meta:
        model = State
        fields = ('name', 'id', 'cities')


class StateDescriptionSerializer(serializers.ModelSerializer):
    cities = CitySerializer(read_only=True, many=True)

    class Meta:
        model = State
        fields = ['id', 'name', 'cities']


class StockTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockType
        fields = ['id', 'name']


class ShipToSerializer(serializers.ModelSerializer):
    city = serializers.SerializerMethodField('get_city')
    state = serializers.SerializerMethodField('get_state')

    def get_state(self, obj):
        return f'{obj.city.state}'

    def get_city(self, obj):
        return f'{obj.city}'

    class Meta:
        model = ShipAddresses
        fields = ['id', 'state', 'city', 'street', 'contact_person', 'phone', 'company_id']


class ShipAddressesUpdateSerializer(serializers.ModelSerializer):

    def update(self, instance, validated_data):
        instance.bld = validated_data.get('bld', instance.bld)
        instance.street = validated_data.get('street', instance.street)
        instance.active = validated_data.get('active', True)
        instance.phone = validated_data.get('phone', instance.phone)
        instance.contact_person = validated_data.get('contact_person', instance.contact_person)
        if validated_data.get('company', instance.company) != instance.company:
            instance.company = CompanyDetails.objects.get(id=validated_data['company'])
        if validated_data.get('city', instance.city) != instance.city:
            instance.city = City.objects.get(id=validated_data['city'])
        instance.transport_type = validated_data.get('transport_type', instance.transport_type)
        instance.save()
        return instance

    class Meta:
        model = ShipAddresses
        fields = '__all__'


class ShipAddressesSerializer(serializers.ModelSerializer):
    city = serializers.SerializerMethodField('get_city')

    def get_or_create(self, validated_data):
        validated_data['city'] = City.objects.get(id=validated_data['city'])
        validated_data['company'] = CompanyDetails.objects.get(id=validated_data['company'])

        obj, _ = ShipAddresses.objects.get_or_create(**validated_data)
        obj.active = True
        obj.save()
        return obj

    def get_city(self, obj):
        return f'{obj.city}'

    def validate(self, data):
        return data

    class Meta:
        model = ShipAddresses
        fields = ['id', 'contact_person', 'phone', 'city', 'street', 'bld', 'company']


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyDetails
        fields = '__all__'


class CompanyDetailsSerializer(serializers.ModelSerializer):
    state = serializers.SerializerMethodField('get_state')
    city = serializers.SerializerMethodField('get_city')
    ship_addr = ShipAddressesSerializer(many=True, read_only=True)

    def get_state(self, obj):
        return f'{obj.city.state}'

    def get_city(self, obj):
        return f'{obj.city}'

    class Meta:
        model = CompanyDetails
        fields = ('id', 'name', 'city', 'state', 'street', 'bld', 'bank_details', 'company_type', 'active', 'ship_addr')
        read_only_fields = ('id',)
        extra_kwargs = {
            'user': {'write_only': True}
        }


class CompanyDetailsUpdateSerializer(serializers.ModelSerializer):
    def update(self, instance, validated_data):
        instance.bank_details = validated_data.get('bank_details', instance.bank_details)
        instance.bld = validated_data.get('bld', instance.bld)
        instance.street = validated_data.get('street', instance.street)
        instance.name = validated_data.get('name', instance.name)
        instance.active = validated_data.get('active', True)
        instance.company_type = validated_data.get('company_type', instance.company_type)
        instance.city_id = validated_data.get('city', instance.city.id)
        instance.save()
        return instance

    def get_or_create(self, validated_data):
        validated_data['city'] = City.objects.get(id=validated_data['city'])
        validated_data['user'] = User.objects.get(id=validated_data['user'])
        validated_data['company_type'] = validated_data['user'].type
        obj, _ = CompanyDetails.objects.get_or_create(**validated_data)
        obj.active = True
        obj.save()
        ship_to = ShipAddresses.objects.filter(company=obj.id).all()
        if ship_to:
            for element in ship_to:
                element.active = True
                element.save()
        return obj

    class Meta:
        model = CompanyDetails
        fields = '__all__'


class UserSerializer(serializers.ModelSerializer):
    user_companies = CompanyDetailsSerializer(read_only=True, many=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email', 'phone', 'user_companies', 'username', 'type')
        read_only_fields = ('id',)


"""_______________________Блок сериализаторов для отображения сток листов____________________________________________"""


class GetItems(serializers.ModelSerializer):
    code = serializers.SerializerMethodField('get_code')
    english_name = serializers.SerializerMethodField('get_english_name')
    scientific_name = serializers.SerializerMethodField('get_scientific_name')
    russian_name = serializers.SerializerMethodField('get_russian_name')
    size = serializers.SerializerMethodField('get_size')
    quantity_in_box = serializers.SerializerMethodField('get_quantity_in_box')

    def get_code(self, obj):
        return obj.item.code

    def get_english_name(self, obj):
        if not obj.english_name:
            return f'{obj.item.english_name}'
        return f'{obj.english_name}'

    def get_scientific_name(self, obj):
        if not obj.scientific_name:
            return f'{obj.item.scientific_name}'
        return f'{obj.scientific_name}'

    def get_russian_name(self, obj):
        if not obj.russian_name:
            return f'{obj.item.russian_name}'
        return f'{obj.russian_name}'

    def get_size(self, obj):
        if not obj.size:
            return f'{obj.item.size}'
        return f'{obj.size}'

    def get_quantity_in_box(self, obj):
        return obj.stock_list.bags_quantity * obj.quantity_per_bag

    def __init__(self, *args, **kwargs):
        request = kwargs.get('context', {}).get('request')
        fields = None
        if request == 'cnee':
            fields = ['id', 'code', 'english_name', 'scientific_name', 'russian_name', 'size',
                      'quantity_per_bag', 'quantity_in_box', 'sale_price']
        elif request == 'shpr':
            fields = ['id', 'code', 'english_name',
                      'scientific_name', 'russian_name',
                      'size', 'offer_price', 'quantity_per_bag',
                      'quantity_in_box', 'status', 'ordered', 'limit']
        elif request == 'shpr/cnee':
            fields = ['id', 'code', 'english_name',
                      'scientific_name', 'russian_name',
                      'size', 'offer_price', 'sale_price', 'quantity_per_bag',
                      'quantity_in_box', 'status', 'ordered', 'limit']
        super(GetItems, self).__init__(*args, **kwargs)
        if fields is not None:
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)

    class Meta:
        model = StockListItem
        fields = '__all__'
        order_by = 'id'


class GetStockItemsSerializer(serializers.ModelSerializer):
    stock_items = serializers.SerializerMethodField('get_stock_items')

    def __init__(self, *args, **kwargs):
        request = kwargs.get('context', {}).get('request')
        fields = None
        if request == 'cnee':
            fields = ['id', 'shipment_date', 'status', 'orders_till_date', 'currency_type', 'currency_rate',
                      'stock_items']
        super(GetStockItemsSerializer, self).__init__(*args, **kwargs)
        if fields is not None:
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)

    def get_stock_items(self, obj):
        if self.context.get("request") == 'cnee':
            obj = StockListItem.objects.select_related('stock_list',
                                                       'item').filter(stock_list=obj.id,
                                                                      status=True).order_by('item__code')
        if self.context.get("request") in ['shpr', 'shpr/cnee', 'staff']:
            obj = StockListItem.objects.select_related('stock_list', 'item').filter(stock_list=obj.id)
        serializer = GetItems(obj, many=True, context={'request': self.context.get('request')})
        return serializer.data

    class Meta:
        model = StockList
        fields = "__all__"


"""______________________Блок сериализаторов для фиксации стоимости фрахта___________________________________________"""


class FreightRateSetSerializer(serializers.ModelSerializer):

    def get_or_create(self, data):
        obj, _ = FreightRatesSet.objects.get_or_create(**data)
        return obj

    class Meta:
        model = FreightRatesSet
        fields = '__all__'


"""_______________________Блок сериализаторов для работы с заказами_______________________________-"""


class OrderedItemsDetails(serializers.ModelSerializer):
    english_name = serializers.SerializerMethodField('get_english_name')
    scientific_name = serializers.SerializerMethodField('get_scientific_name')
    russian_name = serializers.SerializerMethodField('get_russian_name')
    quantity = serializers.SerializerMethodField('get_quantity')
    sale_price = serializers.SerializerMethodField('get_sale_price')
    offer_price = serializers.SerializerMethodField('get_offer_price')
    sale_amount = serializers.SerializerMethodField('get_sale_amount')
    offer_amount = serializers.SerializerMethodField('get_offer_amount')

    def __init__(self, *args, **kwargs):
        request = kwargs.get('context', {}).get('request')
        fields = None
        if request == 'cnee':
            fields = ['id', 'english_name', 'scientific_name', 'russian_name', 'bags', 'quantity', 'sale_price',
                      'sale_amount']
        super(OrderedItemsDetails, self).__init__(*args, **kwargs)
        if request == 'staff':
            fields = ['id', 'english_name', 'scientific_name',
                      'russian_name', 'bags', 'quantity', 'offer_price', 'offer_amount', 'sale_price', 'sale_amount']
        if request == 'shpr':
            fields = ['id', 'english_name', 'scientific_name',
                      'russian_name', 'bags', 'quantity', 'offer_price', 'offer_amount']

        if fields is not None:
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)

    def get_english_name(self, obj):
        if not obj.stock_list_item.english_name:
            return obj.stock_list_item.item.english_name
        return obj.stock_list_item.english_name

    def get_scientific_name(self, obj):
        if not obj.stock_list_item.scientific_name:
            return obj.stock_list_item.item.scientific_name
        return obj.stock_list_item.scientific_name

    def get_russian_name(self, obj):
        if not obj.stock_list_item.russian_name:
            return obj.stock_list_item.item.russian_name
        return obj.stock_list_item.russian_name

    def get_quantity(self, obj):
        return obj.stock_list_item.quantity_per_bag

    def get_offer_price(self, obj):
        return obj.stock_list_item.offer_price * obj.stock_list_item.stock_list.currency_rate

    def get_sale_price(self, obj):
        return obj.stock_list_item.sale_price * obj.stock_list_item.stock_list.currency_rate

    def get_sale_amount(self, obj):
        return (obj.stock_list_item.quantity_per_bag * obj.bags) * obj.stock_list_item.stock_list.currency_rate

    def get_offer_amount(self, obj):
        return (obj.stock_list_item.offer_price * (
                obj.bags * obj.stock_list_item.quantity_per_bag)) * obj.stock_list_item.stock_list.currency_rate

    class Meta:
        model = OrderedItems
        fields = '__all__'


class OrderSerializer(serializers.ModelSerializer):
    ordered_items = serializers.SerializerMethodField('get_ordered_items')
    total_offer_amount = serializers.SerializerMethodField('get_offer_amount')
    total_sale_amount = serializers.SerializerMethodField('get_sale_amount')

    def __init__(self, *args, **kwargs):
        request = kwargs.get('context', {}).get('request')
        fields = None
        if request == 'cnee':
            fields = ['id', 'ordered_items', 'total_sale_amount', 'created_at', 'updated_at', 'shipment_date',
                      'status', 'user', 'ship_to']
        super(OrderSerializer, self).__init__(*args, **kwargs)
        if request in ['staff']:
            fields = ['id', 'ordered_items', 'total_offer_amount', 'total_sale_amount', 'created_at', 'updated_at',
                      'shipment_date',
                      'status', 'user', 'ship_to']
        if request == 'shpr':
            fields = ['id', 'ordered_items', 'total_offer_amount', 'created_at', 'updated_at',
                      'shipment_date',
                      'status', 'user', 'ship_to']
        if fields is not None:
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)

    def get_sale_amount(self, obj):
        items = OrderedItems.objects.select_related('stock_list_item').filter(order=obj.id,
                                                                              status=True)
        amount = 0
        for element in items:
            amount += element.stock_list_item.sale_price * (element.bags * element.stock_list_item.quantity_per_bag)
        if not amount:
            return None
        return amount * obj.stock_list.currency_rate

    def get_offer_amount(self, obj):
        items_obj = OrderedItems.objects.select_related('order__stock_list', 'stock_list_item__item').filter(
            order=obj.id,
            status=True)
        sum = 0
        for item in items_obj:
            sum += (item.stock_list_item.offer_price * (
                    item.stock_list_item.quantity_per_bag * item.bags)) * item.stock_list_item.stock_list.currency_rate
        return sum

    def get_ordered_items(self, obj):
        obj = OrderedItems.objects.select_related('order__stock_list', 'stock_list_item__item').filter(order=obj.id,
                                                                                                       status=True)
        if not obj:
            return None
        return OrderedItemsDetails(obj, many=True, context={'request': self.context.get('request')}).data

    def get_or_create(self, data):
        items = data.pop('items')
        data['shipment_date'] = data['stock_list'].shipment_date
        order, _ = Order.objects.get_or_create(**data)
        return order, items, _

    def update(self, instance, validated_data):
        instance.user = validated_data.get('order', instance.user)
        instance.ship_to = validated_data.get('ship_to', instance.ship_to)
        instance.created_at = validated_data.get('created_at', instance.created_at)
        instance.updated_at = validated_data.get('updated_at', dt.now())
        instance.shipment_date = validated_data.get('shipment_date', instance.shipment_date)
        instance.stock_list = validated_data.get('stock_list', instance.stock_list)
        instance.status = validated_data.get('status', instance.status)
        instance.save()
        return instance

    class Meta:
        model = Order
        fields = '__all__'


"""______________________Блок сериализаторов для работы со сток листами_____________________________________-"""


class GetStockCneeSerializer(serializers.ModelSerializer):
    """ Сериализатор для получения сток листов клиентами """
    stock_type = serializers.SlugRelatedField('name', read_only=True)
    company = serializers.SlugRelatedField('name', read_only=True)

    class Meta:
        model = StockList
        exclude = ('freight_rate', 'ship_from')


class GetStockShprSerizlier(serializers.ModelSerializer):
    """ Сериализатор для получения сток листов поставщиками """

    class Meta:
        model = StockList
        fields = '__all__'


class GetStockStaffSerializator(serializers.ModelSerializer):
    """ Сериализатор для получения сток листов работниками """
    company = CompanySerializer(read_only=True)
    ship_from = ShipToSerializer(read_only=True)
    stock_type = serializers.SlugRelatedField('name', read_only=True)

    class Meta:
        model = StockList
        fields = '__all__'


class StockListCreateSerializer(serializers.ModelSerializer):
    """ Сериализатор для создания и обновления сток листов """

    def validate_company(self, value):
        user = self.context["request"].user
        if value.user != user:
            raise VE(['not belongs to user'])
        return value

    def validate_ship_from(self, value):
        user = self.context["request"].user
        if value.company.user != user:
            raise VE(['not belongs to user company'])
        return value

    def validate_orders_till_date(self, value):
        if value < date.today():
            raise VE(['incorrect, finishing orders must be later than today'])
        return value

    def validate_shipment_date(self, value):
        if value < date.today() + td(days=7):
            raise VE(['shipment date mustbe not earlier than 7 days from today'])
        return value

    def get_or_create(self, validated_data):
        validated_data['company'] = CompanyDetails.objects.filter(id=validated_data['company']).first()
        validated_data['ship_from'] = ShipAddresses.objects.filter(id=validated_data['ship_from']).first()
        validated_data['stock_type'] = StockType.objects.filter(id=validated_data['stock_type']).first()
        if validated_data['transport_type'] in ['Truck', 'Автомобиль']:
            validated_data['freight_rate'] = 0.01
        obj, _ = StockList.objects.get_or_create(**validated_data)
        return obj

    def update(self, instance, validated_date):
        pass

    class Meta:
        model = StockList
        fields = '__all__'


class StockUpdateShprSerializer(serializers.ModelSerializer):
    """ Сериализатор для обновления стока поставщиками """

    def validate_company(self, value):
        user = self.context["request"].user
        if value.user != user:
            raise VE(['not belongs to user'])
        return value

    def validate_ship_from(self, value):
        user = self.context["request"].user
        if not value.company.user != user:
            raise VE(['not belongs to user company'])
        return value

    def validate_orders_till_date(self, value):
        if value < date.today():
            raise VE(['incorrect, finishing orders must be later than today'])
        return value

    def validate_shipment_date(self, value):
        if value < date.today() + td(days=7):
            raise VE(['shipment date mustbe not earlier than 7 days from today'])
        return value

    def update(self, instance, validated_data):
        # serializers.raise_errors_on_nested_writes('updated', self, validated_data)
        if validated_data.get('status'):
            status = validated_data['status']
            if status == 'closed':
                instance.status = status
            else:
                instance.status = 'updated'
        if validated_data.get('company'):
            instance.company = CompanyDetails.objects.get(id=validated_data['company'])
        if validated_data.get('ship_from'):
            instance.ship_from = ShipAddresses.objects.get(id=validated_data['ship_from'])
        instance.orders_till_date = validated_data.get('orders_till_date', instance.orders_till_date)
        instance.shipment_date = validated_data.get('shipment_date', instance.shipment_date)
        if validated_data.get('stock_type'):
            instance.stock_type = StockType.objects.get(id=validated_data['stock_type'])
        instance.freight_rate = validated_data.get('freight_rate', instance.freight_rate)
        instance.transport_type = validated_data.get('transport_type', instance.transport_type)
        instance.bags_quantity = validated_data.get('bags_quantity', instance.bags_quantity)
        instance.box_weight = validated_data.get('box_weight', instance.box_weight)
        instance.currency_type = validated_data.get('currency_type', instance.currency_type)

        instance.save()
        return instance

    class Meta:
        model = StockList
        fields = ['company', 'ship_from', 'orders_till_date',
                  'shipment_date', 'stock_type', 'bags_quantity',
                  'box_weight', 'freight_rate', 'transport_type',
                  'currency_type']
        extra_kwargs = {'company': {'required': False},
                        'ship_from': {'required': False},
                        'orders_till_date': {'required': False},
                        'shipment_date': {'required': False},
                        'stock_type': {'required': False},
                        'bags_quantity': {'required': False},
                        'box_weight': {'required': False},
                        'freight_rate': {'required': False},
                        'transport_type': {'required': False},
                        'currency_type': {'required': False}
                        }


class StockUpdateStaffSerializer(serializers.ModelSerializer):
    """ Сериализатор для обновления сток листа пользователем staff """

    def validate_orders_till_date(self, value):
        if value < date.today():
            raise VE(['incorrect, finishing orders must be later than today'])
        return value

    def validate_shipment_date(self, value):
        if value < date.today() + td(days=7):
            raise VE(['shipment date mustbe not earlier than 7 days from today'])
        return value

    def update(self, instance, validated_data):
        instance.orders_till_date = validated_data.get('orders_till_date', instance.orders_till_date)
        instance.shipment_date = validated_data.get('shipment_date', instance.shipment_date)
        if validated_data.get('stock_type'):
            instance.stock_type = StockType.objects.get(id=validated_data['stock_type'])
        instance.freight_rate = validated_data.get('freight_rate', instance.freight_rate)
        instance.transport_type = validated_data.get('transport_type', instance.transport_type)
        instance.bags_quantity = validated_data.get('bags_quantity', instance.bags_quantity)
        instance.box_weight = validated_data.get('box_weight', instance.box_weight)
        instance.currency_type = validated_data.get('currency_type', instance.currency_type)
        instance.currency_rate = validated_data.get('currency_rate', instance.currency_type)
        instance.status = validated_data.get('status', instance.status)
        instance.name = validated_data.get('name', 'no_name')
        instance.save()
        return instance

    class Meta:
        model = StockList
        fields = ['orders_till_date',
                  'shipment_date', 'stock_type', 'bags_quantity',
                  'box_weight', 'freight_rate', 'transport_type',
                  'currency_type', 'currency_rate', 'status', 'name']
        extra_kwargs = {'orders_till_date': {'required': False},
                        'shipment_date': {'required': False},
                        'stock_type': {'required': False},
                        'bags_quantity': {'required': False},
                        'box_weight': {'required': False},
                        'freight_rate': {'required': False},
                        'transport_type': {'required': False},
                        'currency_type': {'required': False},
                        'currency_rate': {'required': True},
                        'status': {'required': False},
                        'name': {'required': True}
                        }


"""___________________Иные сериализаторы______________________"""


class StockItemUpdateSerializer(serializers.ModelSerializer):
    def update(self, instance, validated_data):
        instance.sale_price = validated_data.get('sale_price', instance.sale_price)
        instance.russian_name = validated_data.get('russian_name', instance.russian_name)
        instance.status = validated_data.get('status', True)
        if instance.sale_price == 0.00:
            instance.status = False
        instance.save()
        return instance

    class Meta:
        model = StockListItem
        fields = ['russian_name', 'sale_price', 'status']


class ItemsCheckSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    bags = serializers.IntegerField()


class ItemUpdateSerializer(serializers.Serializer):
    code = serializers.CharField()
    scientific_name = serializers.CharField()
    english_name = serializers.CharField()
    size = serializers.CharField()
    offer_price = serializers.DecimalField(max_digits=7, decimal_places=2)
    quantity_per_bag = serializers.IntegerField()
    limit = serializers.IntegerField()


"""________________Блок сериализаторов для получения заказов по сток листу________________"""
""" сериализатор для получения заказанных пользователем группы Shpr или Shpr/Cnee  """


class GetOrderedItemsShpr(serializers.ModelSerializer):
    code = serializers.SerializerMethodField('get_code')
    english_name = serializers.SerializerMethodField('get_english_name')
    scientific_name = serializers.SerializerMethodField('get_scientific_name')
    price = serializers.SerializerMethodField('get_price')
    ordered = serializers.SerializerMethodField('get_qty')
    amount = serializers.SerializerMethodField('get_amount')

    def get_amount(self, obj):
        return obj.stock_list_item.offer_price * (obj.bags * obj.stock_list_item.quantity_per_bag)

    def get_qty(self, obj):
        return obj.bags * obj.stock_list_item.quantity_per_bag

    def get_price(self, obj):
        return obj.stock_list_item.offer_price

    def get_scientific_name(self, obj):
        if not obj.stock_list_item.scientific_name:
            return obj.stock_list_item.item.scientific_name
        return obj.stock_list_item.scientific_name

    def get_english_name(self, obj):
        if not obj.stock_list_item.english_name:
            return obj.stock_list_item.item.english_name
        return obj.stock_list_item.english_name

    def get_code(self, obj):
        return obj.stock_list_item.item.code

    class Meta:
        model = OrderedItems
        exclude = ['status', 'id']


class GetOrdersShpr(serializers.ModelSerializer):
    orders = serializers.SerializerMethodField('get_orders')
    total_amount = serializers.SerializerMethodField('get_total_amount')

    def get_total_amount(self, obj):
        orders = OrderedItems.objects.select_related('stock_list_item__item',
                                                     'order'). \
            filter(stock_list_item__stock_list=obj, status=True).exclude(order__status='Deleted')
        return sum(
            [order.stock_list_item.offer_price * (order.bags * order.stock_list_item.quantity_per_bag) for order in
             orders])

    def get_orders(self, obj):
        orders = OrderedItems.objects.select_related('stock_list_item__item',
                                                     'order'). \
            filter(stock_list_item__stock_list=obj, status=True).exclude(order__status='Deleted')
        return GetOrderedItemsShpr(orders, many=True).data,

    class Meta:
        model = StockList
        exclude = ('currency_rate',)


""" сериализатор для получения заказанных позиций пользователем группы Cnee или Shpr/Cnee """


class GetOrderedItemsCnee(serializers.ModelSerializer):
    qty = serializers.SerializerMethodField('get_qty')
    price = serializers.SerializerMethodField('get_price')
    amount = serializers.SerializerMethodField('get_amount')
    name = serializers.SerializerMethodField('get_name')

    def get_name(self, obj):
        return f'{obj.stock_list_item.item.english_name}/ ' \
               f'{obj.stock_list_item.item.scientific_name}/ ' \
               f'{obj.stock_list_item.item.russian_name}/' \
               f'{obj.stock_list_item.item.size}'

    def get_amount(self, obj):
        return obj.stock_list_item.sale_price * (obj.bags * obj.stock_list_item.quantity_per_bag)

    def get_price(self, obj):
        return obj.stock_list_item.sale_price

    def get_qty(self, obj):
        return obj.stock_list_item.quantity_per_bag * obj.bags

    class Meta:
        model = OrderedItems
        exclude = ['status', 'order', 'id']


class GetOrdersCnee(serializers.ModelSerializer):
    items = serializers.SerializerMethodField('get_orders')
    total_amount = serializers.SerializerMethodField('get_total_amount')

    def get_total_amount(self, obj):
        obj = OrderedItems.objects.select_related('stock_list_item', 'stock_list_item__item').filter(order=obj,
                                                                                                     status=True)
        result = [i.stock_list_item.sale_price * (i.bags * i.stock_list_item.quantity_per_bag) for i in obj]
        return sum(result)

    def get_orders(self, obj):
        obj = OrderedItems.objects.select_related('stock_list_item', 'stock_list_item__item').filter(order=obj,
                                                                                                     status=True)
        serializer = GetOrderedItemsCnee(obj, many=True)

        return serializer.data

    class Meta:
        model = Order
        exclude = ['user', ]


""" сериализатор для получения заказанных позиций пользователем группы Staff  """


class GetOrderedItemsStaff(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    qty = serializers.SerializerMethodField()
    offer_price = serializers.SerializerMethodField()
    sale_price = serializers.SerializerMethodField()
    offer_amount = serializers.SerializerMethodField()
    sale_amount = serializers.SerializerMethodField()

    def get_sale_amount(self, obj):
        return obj.stock_list_item.sale_price * (obj.stock_list_item.quantity_per_bag * obj.bags)

    def get_offer_amount(self, obj):
        return obj.stock_list_item.offer_price * (obj.stock_list_item.quantity_per_bag * obj.bags)

    def get_sale_price(self, obj):
        return obj.stock_list_item.sale_price

    def get_offer_price(self, obj):
        return obj.stock_list_item.offer_price

    def get_qty(self, obj):
        return obj.stock_list_item.quantity_per_bag * obj.bags

    def get_name(self, obj):
        return f'{obj.stock_list_item.item.english_name}/ ' \
               f'{obj.stock_list_item.item.scientific_name}/ ' \
               f'{obj.stock_list_item.item.russian_name}/' \
               f'{obj.stock_list_item.item.size}'

    class Meta:
        model = OrderedItems
        exclude = ['status', ]


class GetOrdersStaff(serializers.ModelSerializer):
    orders = serializers.SerializerMethodField()
    amounts = serializers.SerializerMethodField()

    def get_amounts(self, obj):
        obj = OrderedItems.objects.select_related('stock_list_item__item').filter(stock_list_item__stock_list=obj,
                                                                                  status=True)
        buy = sum([i.stock_list_item.offer_price * (i.bags * i.stock_list_item.quantity_per_bag) for i in obj])
        sale = sum([i.stock_list_item.sale_price * (i.bags * i.stock_list_item.quantity_per_bag) for i in obj])
        return {'buy': buy, 'sale': sale, 'profit': sale - buy}

    def get_orders(self, obj):
        print(2)
        obj = OrderedItems.objects.select_related('stock_list_item__item').filter(stock_list_item__stock_list=obj,
                                                                                  status=True)
        serializer = GetOrderedItemsStaff(obj, many=True)
        return serializer.data

    class Meta:
        model = StockList
        fields = '__all__'
