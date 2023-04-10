from django.contrib.auth.password_validation import validate_password
from django.shortcuts import render
import xlrd
from requests import get
import urllib.request
from django.contrib.auth.models import User, Group
from rest_framework import viewsets
from rest_framework import permissions
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from django.http import JsonResponse
from backend.models import User, State, ConfirmEmailToken, City, FreightRates, StockType, CompanyDetails, ShipAddresses
from backend.serializers import StateSerializer, UserSerializer, CitySerializer, \
    StateDescriptionSerializer, FreightRatesSerializer, CityFreightSerializer, StockTypeSerializer, \
    CompanyDetailsSerializer
from backend.signals import new_user_registered
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
import ssl
from ujson import loads as load_json
from rest_framework.generics import ListAPIView

class UserShipTo(APIView):
    def get(self, request, pk=None, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type not in ['shpr', 'cnee']:
            return JsonResponse({'Status': False, 'Error': 'Only for suppliers or cnee'}, status=403)

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type not in ['shpr', 'cnee']:
            return JsonResponse({'Status': False, 'Error': 'Only for suppliers or cnee'}, status=403)
        if {'city', 'company', 'street', 'bld', 'contact_person', 'phone'}.issubset(request.data):
            pass

    def put(self, request, pk=None, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type not in ['shpr', 'cnee']:
            return JsonResponse({'Status': False, 'Error': 'Only for suppliers or cnee'}, status=403)
        if not pk:
            return JsonResponse({'error': 'Method put not allowed'})
        try:
            instance = ShipAddresses.objects.get(id=pk, user_id=request.user.id)
        except:
            return JsonResponse({'error': 'object doen not exvcists'})
class UserCompanies(APIView):
    """
    Работа с компаниями покупателя и поставщика, один пользователь может представлять несколько компаний,
    вне зависимости от того поставщик он или покупатель.
    Также пользователь может быть одновременно поставщиком и покупателем
    """
    def get(self, request, pk=None, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type not in ['shpr', 'cnee', 'shpr/cnee']:
            return JsonResponse({'Status': False, 'Error': 'Only for shpr, cnee or shpr/cnee'}, status=403)
        if pk:
            obj = CompanyDetails.objects.filter(id=pk, active=True)
            serializer = CompanyDetailsSerializer(obj, many=True)
            return Response(serializer.data)
        obj = CompanyDetails.objects.select_related('city', 'user').filter(user_id=request.user.id, active=True).all()
        serializer = CompanyDetailsSerializer(obj, many=True)
        return Response(serializer.data)

    """
    Добавление компаний к пользователю подразумевает только добавление одной компании за раз
    """
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type not in ['shpr', 'cnee', 'shpr/cnee']:
            return JsonResponse({'Status': False, 'Error': 'Only for shpr, cnee or shpr/cnee'}, status=403)
        if {'name', 'state', 'city', 'street', 'bld', 'bank_details'}.issubset(request.data):
            try:
                obj = CompanyDetails.objects.get(name=request.data['name'])
                obj.active = True
                obj.save()
                return JsonResponse({'status': False, 'come': 'back'})
            except:
                state, _ = State.objects.get_or_create(name=request.data['state'].capitalize())
                city, _ = City.objects.get_or_create(name=request.data['city'].capitalize(),
                                                     state_id=state.id)
                obj, _ = CompanyDetails.objects.get_or_create(user_id=request.user.id,
                                                              name=request.data['name'],
                                                              city=city,
                                                              street=request.data['street'],
                                                              bld=request.data['bld'],
                                                              bank_details=request.data['bank_details'],
                                                              company_type=request.user.type)

            return Response({'created': obj.id})
        return JsonResponse({'status': 'incorrect fields'})

    def put(self, request, pk=None, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type not in ['shpr', 'cnee', 'shpr/cnee']:
            return JsonResponse({'Status': False, 'Error': 'Only for shpr, cnee or shpr/cnee'}, status=403)
        if not pk:
            return JsonResponse({'error': 'Method put not allowed'})
        if not {'company_type'}.issubset(request.data):
            request.data['company_type'] = request.user.type
        try:
            instance = CompanyDetails.objects.get(id=pk, user_id=request.user.id)
            print('instance')
        except:
            return JsonResponse({'error': 'object doen not exvcists'})
        print(request.data)
        serializer = CompanyDetailsSerializer(data=request.data, instance=instance)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return JsonResponse({'status': f'item with pk{pk} updated'})

    def delete(self, request, pk=None, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        elif request.user.type not in ['shpr', 'cnee', 'shpr/cnee']:
            return JsonResponse({'Status': False, 'Error': 'Only for shpr, cnee or shpr/cnee'}, status=403)
        elif not pk:
            return JsonResponse({'error': 'no PK'})
        obj = CompanyDetails.objects.get(id=pk, user_id=request.user.id)
        obj.active = False
        obj.save()
        return JsonResponse({'status': f'{pk} deleted'})




class SetStockTypes(APIView):
    """
    Класс загрузки типов сток листов в дб и получения их списка, осуществляется только пользователями группы staff
    """
    def check_user(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type != 'staff':
            return JsonResponse({'Status': False, 'Error': 'Только для персонала'}, status=403)
        return True

    def post(self, request, *args, **kwargs):
        self.check_user(request)
        if {'stock_types'}.issubset(request.data):
            for element in request.data['stock_types']:
                StockType.objects.get_or_create(name=element['name'].capitalize())
            return JsonResponse({'status': 'stock_types finished'})

    def get(self, request, *args, **kwargs):
        self.check_user(request)
        obj = StockType.objects.all()
        serializer = StockTypeSerializer(obj, many=True)
        return Response(serializer.data)
    """
    удаление не предусматривается
    """

class SetFreightRates(APIView):
    """"
    Загрузка значений стоимости фрахта досутпно только пользователям групы staff
    """
    def check_user(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type != 'staff':
            return JsonResponse({'Status': False, 'Error': 'Только для персонала'}, status=403)
        return True

    """
    Загрузка возможна только по ссылке с файлом формата xls(не XLSX)
    """
    def post(self, request, *args, **kwargs):
        self.check_user(request)
        if not {'url', 'state'}.issubset(request.data):
            return JsonResponse({'status': False, 'message': 'incorrect fields, need url and state'})

        url = request.data.get('url')
        validate_url = URLValidator()
        try:
            validate_url(url)
        except ValidationError as e:
            return JsonResponse({'status': False, 'error': str(e)})

        ssl._create_default_https_context = ssl._create_unverified_context  # проблема с SSL сертами
        urllib.request.urlretrieve(url, 'freightrates.xls')
        wb = xlrd.open_workbook('freightrates.xls')
        sheet = wb.sheet_by_index(0)
        state, _ = State.objects.get_or_create(name=request.data['state'].capitalize())  # идентифицируется страна
        """ 
        Предполагается, что фаил идет всегда одного вида, меняется лишь количество строк 
        """
        for rownum in range(1, sheet.nrows):  # предполагается, что в файле первая строка - заголовок
            row = sheet.row_values(rownum)
            city, _ = City.objects.get_or_create(name=row[1].capitalize(), state_id=state.id)
            FreightRates.objects.update_or_create(POL=row[0], city_id=city.id, price=row[2], minimal_weight=row[3])

        return JsonResponse({'stat': 'ok'})

    """ 
    Получение информации по стоимостям фрахта для всех городов по названию страны или для определнного города по его названию
    """

    def get(self, request, *args, **kwargs):
        self.check_user(request)
        if {'city'}.issubset(request.data):
            obj = City.objects.filter(name=request.data['city']).first()
            serializer = CityFreightSerializer(obj)
            return Response(serializer.data)
        obj = City.objects.all()
        return Response(CityFreightSerializer(obj, many=True).data)

    """
    Удаление не предусмотрено
    """



class UploadStateCity(APIView):
    # проверка аутентификации пользователя и его статус.
    def check_user(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type != 'staff':
            return JsonResponse({'Status': False, 'Error': 'Только для персонала'}, status=403)
        return True

    """ внесениюе в дб информации по странам и городам """

    def post(self, request, *args, **kwargs):
        self.check_user(request)
        if {'state'}.issubset(request.data):
            for state in request.data['state']:
                obj, _ = State.objects.get_or_create(name=state['name'].capitalize())
                for element in state['cities']:
                    City.objects.get_or_create(name=element['name'].capitalize(), state_id=obj.id)
            return JsonResponse({'status': 'State and cities filled successfully'})
        return JsonResponse({"status": "incorrect fields"})

    """ получение информации о городах по названию страны, ил страны или польная выгрузка """

    def get(self, request, pk=None, *args, **kwargs):
        self.check_user(request)
        query_set = State.objects.all()
        if pk:
            query_set = State.objects.filter(id=pk).all()
        elif {'state'}.issubset(request.data):
            query_set = State.objects.filter(name=request.data['state'].capitalize()).all()
        elif not query_set:
            return JsonResponse({'status': 'not in DB'})
        return Response(StateSerializer(query_set, many=True).data)


class LoginAccount(APIView):
    """
    Класс для авторизации пользователей
    """

    # Авторизация методом POST
    def post(self, request, *args, **kwargs):
        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, username=request.data['email'], password=request.data['password'])
            if user is not None:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)

                    return JsonResponse({'Status': True, 'Token': token.key})

            return JsonResponse({'Status': False, 'Errors': 'Не удалось авторизовать'})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class AccountDetails(APIView):
    """
    Класс для работы данными пользователя
    """

    # получить данные
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    # Редактирование методом POST
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        # проверяем обязательные аргументы
        if 'password' in request.data:
            errors = {}
            # проверяем пароль на сложность
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = []
                # noinspection PyTypeChecker
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}})
            else:
                request.user.set_password(request.data['password'])
        # проверяем остальные данные
        user_serializer = UserSerializer(request.user, data=request.data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({'Status': True})
        else:
            return JsonResponse({'Status': False, 'Errors': user_serializer.errors})


class RegisterAccount(APIView):
    """
    Для регистрации покупателей
    """
    # Регистрация методом POST
    def post(self, request, *args, **kwargs):
        # проверяем обязательные аргументы
        if {'first_name', 'last_name', 'email', 'password', 'type'}.issubset(request.data):
            errors = {}
            # проверяем пароль на сложность
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = []
                # noinspection PyTypeChecker
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}})
            else:
                # проверяем данные для уникальности имени пользователя
                request.data._mutable = True
                request.data.update({})

                user_serializer = UserSerializer(data=request.data)
                if user_serializer.is_valid():
                    # сохраняем пользователя
                    user = user_serializer.save()
                    user.set_password(request.data['password'])
                    user.save()
                    new_user_registered.send(sender=self.__class__, user_id=user.id)
                    return JsonResponse({'Status': True})
                else:
                    return JsonResponse({'Status': False, 'Errors': user_serializer.errors})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class ConfirmAccount(APIView):
    """
    Класс для подтверждения почтового адреса
    """

    # Регистрация методом POST
    def post(self, request, *args, **kwargs):
        # проверяем обязательные аргументы
        if {'email', 'token'}.issubset(request.data):
            token = ConfirmEmailToken.objects.filter(user__email=request.data['email'],
                                                     key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return JsonResponse({'Status': True})
            else:
                return JsonResponse({'Status': False, 'Errors': 'Неправильно указан токен или email'})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})
