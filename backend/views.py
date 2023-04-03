from django.contrib.auth.password_validation import validate_password
from django.shortcuts import render

from requests import get
from django.contrib.auth.models import User, Group
from rest_framework import viewsets
from rest_framework import permissions
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from django.http import JsonResponse
from backend.models import User, State, ConfirmEmailToken, City, FreightRates
from backend.serializers import StateSerializer, UserSerializer, CitySerializer, StateDescriptionSerializer
from backend.signals import new_user_registered
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from ujson import loads as load_json
from rest_framework.generics import ListAPIView


class SetFreightRates(APIView):
    def check_user(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type != 'staff':
            return JsonResponse({'Status': False, 'Error': 'Только для персонала'}, status=403)
        return True

    def post(self, request, *args, **kwargs):
        self.check_user(request)
        print(request.data)


    def get(self, request, *args, **kwargs):
        pass

    def delete(self, request, *args, **kwargs):
        pass




class UploadStateCity(APIView):
    # проверка аутентификации пользователя и его статус.
    def check_user(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        if request.user.type != 'staff':
            return JsonResponse({'Status': False, 'Error': 'Только для персонала'}, status=403)
        return True

    # внесениюе в дб информации по странам и городам
    def post(self, request, *args, **kwargs):
        self.check_user(request)
        if {'state',}.issubset(request.data):
            for state in request.data['state']:
                obj, _ = State.objects.get_or_create(name=state['name'])
                for element in state['cities']:
                    City.objects.get_or_create(name=element['name'], state_id=obj)
            return JsonResponse({'status': 'State and cities filled successfully'})
        return JsonResponse({"status": "incorrect fields"})

    # получение информации по странам и городам в дб.
    def get(self, request, pk=None, *args, **kwargs):
        self.check_user(request)
        if pk:
            query_set = State.objects.filter(id=pk).all()
            if not query_set:
                return JsonResponse({'status': 'not in DB'})
        query_set = State.objects.all()
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
        print(request.user)
        # print(request.data)
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

