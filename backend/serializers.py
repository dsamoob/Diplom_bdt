from backend.models import User, CompanyDetails, State, City, ShipTo, FreightRates, StockType
from rest_framework import serializers


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ('id', 'name')

class FreightRatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = FreightRates
        fields = ['POL', 'minimal_weight', 'price']


class CityFreightSerializer(serializers.ModelSerializer):
    cities = FreightRatesSerializer(many=True)
    class Meta:
        model = City
        fields = ['name', 'cities']


class StateSerializer(serializers.ModelSerializer):
    cities = CitySerializer(many=True)
    class Meta:
        model = State
        fields = ('name', 'id', 'cities')


# class CitySerializer(serializers.ModelSerializer):
#     state = StateSerializer(read_only=True, many=True)
#
#     class Meta:
#         model = City
#         fields = ('id', 'name', 'state')


class StateDescriptionSerializer(serializers.ModelSerializer):
    cities = CitySerializer(read_only=True, many=True)

    class Meta:
        model = State
        fields = ['id', 'name', 'cities']

class StockTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockType
        fields = ['id', 'name']

####___________________

class CompanyDetailsSerializer(serializers.ModelSerializer):
    city = CitySerializer(read_only=True, many=True)

    class Meta:
        model = CompanyDetails
        fields = ('id', 'name',  'city', 'street', 'bld', 'bank_details')
        read_only_fields = ('id',)
        extra_kwargs = {
            'user': {'write_only': True}
        }


class UserSerializer(serializers.ModelSerializer):
    company_details = CompanyDetailsSerializer(read_only=True, many=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email',  'phone', 'company_details')
        read_only_fields = ('id',)
