from backend.models import User, CompanyDetails, State, City, ShipAddresses, FreightRates, StockType, StockList
from rest_framework import serializers
from datetime import datetime as dt
from datetime import timedelta as td
from django.core.exceptions import ValidationError


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ('id', 'name')


class FreightRatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = FreightRates
        fields = ['POL', 'minimal_weight', 'price']


class CityFreightSerializer(serializers.ModelSerializer):
    POLs = FreightRatesSerializer(many=True)

    class Meta:
        model = City
        fields = ['id', 'name', 'POLs']


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
        fields = ['id', 'state', 'city', 'street', 'contact_person', 'phone', 'ship_target', 'company_id' ]

class ShipAddressesUpdateSerializer(serializers.ModelSerializer):

    def update(self, instance, validated_data):
        instance.bld = validated_data.get('bld', instance.bld)
        instance.street = validated_data.get('street', instance.street)
        instance.active = validated_data.get('active', True)
        instance.ship_target = validated_data.get('ship_target', instance.ship_target)
        instance.phone = validated_data.get('phone', instance.phone)
        instance.contact_person = validated_data.get('contact_person', instance.contact_person)
        instance.company = validated_data.get('company', instance.company)
        instance.city = validated_data.get('city', instance.city)

        instance.save()
        return instance
    class Meta:
        model = ShipAddresses
        fields = '__all__'


class ShipAddressesSerializer(serializers.ModelSerializer):
    city = serializers.SerializerMethodField('get_city')

    def create(self, validated_data):
        validated_data['city'] = City.objects.get(id=validated_data['city'])
        validated_data['company'] = CompanyDetails.objects.get(id=validated_data['company'])
        return ShipAddresses.objects.create(**validated_data)

    def get_city(self, obj):
        return f'{obj.city}'

    def validate(self, data):
        return data

    class Meta:
        model = ShipAddresses
        fields = ['id', 'ship_target', 'contact_person', 'phone', 'city', 'street', 'bld', 'company']


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


class StockListCreateSerializer(serializers.ModelSerializer):

    def update(self, instance, validated_data):
        print(instance)
        instance.orders_till_date = validated_data.get('orders_till_date', instance.orders_till_date)
        instance.shipment_date = validated_data.get('shipment_date', instance.shipment_date)
        instance.bags_quantity = validated_data.get('bags_quantity', instance.bags_quantity)
        instance.currency_rate = validated_data.get('currency_rate', instance.currency_rate)
        instance.status = validated_data.get('status', instance.status)
        instance.box_weight = validated_data.get('box_weight', instance.box_weight)
        instance.company = validated_data.get('company', instance.company)
        instance.stock_type = validated_data.get('stock_type', instance.stock_type)
        instance.ship_from = validated_data.get('ship_from', instance.ship_from)
        instance.currency_type = validated_data.get('currency_type', instance.currency_type)
        instance.transport_type = validated_data.get('transport_type', instance.transport_type)
        instance.save()
        return instance

    def get_or_create(self, validated_data):
        validated_data['company'] = CompanyDetails.objects.filter(id=validated_data['company']).first()
        validated_data['ship_from'] = ShipAddresses.objects.filter(id=validated_data['ship_from']).first()
        validated_data['stock_type'] = StockType.objects.filter(id=validated_data['stock_type']).first()
        obj, _ = StockList.objects.get_or_create(**validated_data)
        return obj




    class Meta:
        model = StockList
        fields = '__all__'

class StockListReadSerializer(serializers.ModelSerializer):

    class Meta:
        model = StockList
        fields = '__all__'
###______________--
class UserSerializer(serializers.ModelSerializer):
    user_companies = CompanyDetailsSerializer(read_only=True, many=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email', 'phone', 'user_companies', 'username', 'type')
        read_only_fields = ('id',)
