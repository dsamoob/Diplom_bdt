from backend.models import User, CompanyDetails, State, City, ShipAddresses, FreightRates, StockType
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
    class Meta:
        model =ShipAddresses
        fields = ['']

class CompanyDetailsSerializer(serializers.ModelSerializer):

    state = serializers.SerializerMethodField('get_state')
    city = serializers.SerializerMethodField('get_city')

    def get_state(self, obj):
        return f'{obj.city}'

    def get_city(self, obj):
        return f'{obj.city.state}'

    def create(self, validated_data):
        print(f'{validated_data=}')
        print(f'{validated_data["user"]}')
        # validated_data['city_id'] = 1
        # validated_data['user_id'] = 1
        print('created func')
        return CompanyDetails.objects.create(**validated_data)

    def update(self, instance, validated_data):
        instance.bank_details = validated_data.get('bank_details', instance.bank_details)
        instance.bld = validated_data.get('bld', instance.bld)
        instance.street = validated_data.get('street', instance.street)
        instance.name = validated_data.get('name', instance.name)
        instance.active = validated_data.get('active', True)
        instance.company_type = validated_data.get('comapny_type', instance.company_type)
        instance.save()
        return instance

    class Meta:
        model = CompanyDetails
        fields = ('id', 'name', 'city', 'state', 'street', 'bld', 'bank_details', 'company_type', 'active')
        read_only_fields = ('id',)
        extra_kwargs = {
            'user': {'write_only': True}
        }


###______________--
class UserSerializer(serializers.ModelSerializer):
    user_companies = CompanyDetailsSerializer(read_only=True, many=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email',  'phone', 'user_companies', 'username', 'type')
        read_only_fields = ('id',)

