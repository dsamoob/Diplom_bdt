import os

from django.contrib.auth.password_validation import validate_password

from django.db.models import Q
import xlrd
from rest_condition import And, Or
from decimal import Decimal
from datetime import date
import urllib.request
from backend.permissions import IsStaff, IsCneeShpr, IsAuthenticated, IsShprorCnShpr
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from django.http import JsonResponse
from backend.models import User, State, ConfirmEmailToken, City, FreightRates, StockType, CompanyDetails,\
    ShipAddresses, StockList, StockListItem, Order, OrderedItems, Item
from backend.serializers import StateSerializer, UserSerializer, CityFreightSerializer, StockTypeSerializer, \
    CompanyDetailsSerializer, ShipToSerializer, CompanyDetailsUpdateSerializer, ShipAddressesUpdateSerializer, \
    ShipAddressesSerializer, ItemUploadingSerializer, StockListCreateSerializer, \
    StockListItemSerializer, OrderSerializer, OrderedItemSerializer, GetStockCneeSerializer, \
    GetStockShprSerizlier, GetStockStaffSerializator, StockUpdateShprSerializer, StockUpdateStaffSerializer,\
    GetStockItemsSerializer

from backend.signals import new_user_registered, new_stock_list, stock_list_update
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
import ssl


class Orders(APIView):
    permission_classes = [Or(And(IsCneeShpr, ), And(IsAuthenticated, IsStaff), )]

    def get(self, request, pk=None, *args, **kwargs):
        if pk:
            order = Order.objects.filter(id=pk, user=request.user.id).first()
            if not order:
                return JsonResponse({'error': f'order with id {pk} not found'})
            serializer = OrderSerializer(order)
            return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        # проверка на актуальность сток листа
        if not StockList.objects.filter(id=request.data['stock_list'], status='offered'):
            return JsonResponse({'stocklist': 'not found'})
        # проверка входящего джсона
        if not {'items', 'ship_to', 'stock_list'}.issubset(request.data) or not isinstance(request.data['items'], list):
            return JsonResponse({'error': 'incorrect fields'})
        request.data['stock_list'] = StockList.objects.get(id=request.data['stock_list'])
        request.data['user'] = request.user
        # проверка адреса получателя на принадлежность пользователю
        ship_to = ShipAddresses.objects.select_related('company').filter(id=request.data['ship_to'],
                                                                         company__user=request.user).first()

        if not ship_to:
            return JsonResponse({'error': f'incorrect ship_to id'})
        # проверка количества заказанного
        if sum([i['bags'] for i in request.data['items']]) % request.data['stock_list'].bags_quantity != 0:
            return JsonResponse({'error': 'incorrect bags quantity'})
        request.data['ship_to'] = ship_to
        # проверка наличия позиций и их количества в наличии
        for item in request.data['items']:
            item_obj = StockListItem.objects.filter(id=item['id'], status=True,
                                                    stock_list=request.data['stock_list'].id).first()
            if not item_obj:
                return JsonResponse({'error': f'incorrect item id: {item["id"]}'})
            if (item_obj.quantity_bag * item['bags']) + item_obj.ordered > item_obj.limit and item_obj.limit != 0:
                return JsonResponse({'status': f'not enough on stock for item  with id: {item["id"]}'})
        # создание самого заказа
        serializer = OrderSerializer(request.data)
        order, items = serializer.get_or_create(data=request.data)
        # создание позиций заказа
        for item in items:
            item_obj = StockListItem.objects.filter(id=item['id'], status=True).first()
            if not item_obj:
                return JsonResponse({'status': f'not available item {item["id"]}'})
            item_obj.ordered = item_obj.ordered + (item_obj.quantity_bag * item['bags'])
            item_obj.save()
            data = {'bags': item['bags'],
                    'amount': item_obj.sale_price * (item['bags'] * item_obj.quantity_bag),
                    'item': item_obj,
                    'order': order}
            serializer = OrderedItemSerializer(data)
            serializer.create_or_update(data=data)
        return JsonResponse({'status': 'successful',
                             'order_id': order.id})

    def put(self, request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'No pk'})
        # пользователь группы staff может только менять статус заказа и дату доставки
        if request.user.type == 'staff':
            if not {'shipment_date', 'status'}.issubset(request.data):
                return JsonResponse({'error': 'incorrect data'})
            try:
                instance = Order.objects.get(id=pk)
            except:
                return JsonResponse({'error': f'incorrect order id: {pk}'})
            serializer = OrderSerializer(request.data)
            serializer.update(validated_data=request.data, instance=instance)

        # пользователь (cnee или shpr/cnee) может изменять только ship-to,
        # статус заказа меняется на updated автоматически
        instance = Order.objects.filter(id=pk, user=request.user).first()
        if not instance:
            return JsonResponse({'error': 'incorrect pk or order not belongs to u'})
        if not {'ship_to'}.issubset(request.data):
            return JsonResponse({'error': 'incorrect data'})
        request.data['ship_to'] = ShipAddresses.objects.select_related('company').filter(company__user=request.user.id,
                                                                                         id=request.data[
                                                                                             'ship_to']).first()
        if not request.data['ship_to']:
            return JsonResponse({'error': f'incorrect ship_to id'})
        request.data['status'] = 'Updated'
        serializer = OrderSerializer(request.data)
        serializer.update(validated_data=request.data, instance=instance)
        return JsonResponse({'ok': 'finished'})


class GetStockItems(APIView):
    permission_classes = (IsAuthenticated,)
    # получение позиций из сток листа

    @staticmethod
    def get(request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'No pk'})
        # получение содержимого сток листов покупателями
        if request.user.type == 'cnee':
            obj = StockList.objects.filter(id=pk, status='offered').first()
            if not obj:
                return JsonResponse({'incorrect id': f'{pk}'})
            # передача через context информации о пользователе
            serializer = GetStockItemsSerializer(obj, context={'request': request.user.type})
            return Response(serializer.data)

        # получение содержимого сток листов пользователями shpr
        elif request.user.type == 'shpr':
            # проверка принадлежности сток листа поставщику
            obj = StockList.objects.select_related('company').filter(id=pk, company__user=request.user).first()
            if not obj:
                return JsonResponse({'incorrect id': f'{pk}'})
            serializer = GetStockItemsSerializer(obj, context={'request': request.user.type})
            return Response(serializer.data)

        # получение содержимого сток листов пользователями shpr/cnee
        elif request.user.type == 'shpr/cnee':
            obj = StockList.objects.select_related('company').filter(id=pk).first()
            if not obj:
                return JsonResponse({'incorrect id': f'{pk}'})
            # проверка принадлежности сток листа пользователю как поставщику
            if obj.company.user == request.user:
                # пользователь получает сток лист как поставщик и как клиент - полная информация
                return Response(GetStockItemsSerializer(obj, context={'request': 'shpr/cnee'}).data)
            # если сток не принадлежит пользователю как поставщику, то пользователь получает его как клиент
            if obj.status == 'offered' and obj.company.user != request.user:
                return Response(GetStockItemsSerializer(obj, context={'request': 'cnee'}).data)
            return JsonResponse({'incorrect id': f'{pk}'})

        # получение содержимого сток листов пользователями staff
        elif request.user.type == 'staff':
            obj = StockList.objects.get(id=pk)
            if not obj:
                return JsonResponse({'incorrect id': f'{pk}'})
            return Response(GetStockItemsSerializer(obj, context={'request': request.user.type}).data)


class StockItemsUpload(APIView):
    permission_classes = (IsAuthenticated, )

    def post(self, request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'No pk'})
        # проверка url
        url = request.data.get('url')
        if url:
            validate_url = URLValidator()
            try:
                validate_url(url)
            except ValidationError as e:
                return JsonResponse({'Status': False, 'Error': str(e)})
        else:
            return JsonResponse({'error': 'no url'})

        # для загрузки позиций из стока поставщиком
        if request.user.type in ['shpr', 'shpr/cnee']:
            # проверка принадлежности сток листа и его актуальности
            stock_obj = StockList.objects.select_related('company').filter(id=pk,
                                                                           company__user=request.user,
                                                                           status='uploaded').first()
            if not stock_obj:
                return JsonResponse({'error': f'stock with id {pk} already closed or offered or not belongs to user'})
            # проверка ранее загруженных позиций, если есть хоть одна позиция в статусе
            # True то любые изменения через view items
            if StockListItem.objects.filter(stock_list=pk, status=True).first():
                return JsonResponse({'error': 'items for this stock list already uploaded'})

            ssl._create_default_https_context = ssl._create_unverified_context
            # создание временного файла
            file_name = f'stock_list_{date.today()}_{stock_obj.company.id}.xls'
            urllib.request.urlretrieve(url, file_name)
            wb = xlrd.open_workbook(file_name)
            sheet = wb.sheet_by_index(0)
            # Проверка шапки файла на соответствие
            if sheet.row_values(0) != ['code',
                                       'english_name',
                                       'scientific_name',
                                       'size',
                                       'price',
                                       'quantity_box',
                                       'limit']:
                # удаление временного файла
                os.remove(file_name)
                return JsonResponse({'error': 'incorrect fields in file'})
            # проход по файлу
            result_list = {}  # создание словаря ошибок
            for rownum in range(1, sheet.nrows):
                row = sheet.row_values(rownum)
                # получение/ создание позиции

                if not all(row[i] for i in range(6)): # проверка заполненности строки
                    result_list[row[0]] = 'not_added'
                    continue
                # поиск ранее созданной позиции
                item = Item.objects.filter(code=row[0],
                                           english_name=row[1],
                                           scientific_name=row[2],
                                           size=row[3],
                                           company=stock_obj.company).first()
                # создание позиции, если она не была найдена
                if not item:
                    info = {'company': stock_obj.company,
                            'code': row[0],
                            'english_name': row[1],
                            'scientific_name': row[2],
                            'size': row[3]}
                    item = ItemUploadingSerializer(info)
                    item = item.get_or_create(data=info)
                # получение создание связки позиция/сток
                instance = StockListItem.objects.filter(stock_list=stock_obj.id,
                                                        item=item.id).first()

                if not instance:
                    data_stock_item = {'item': item,
                                       'stock_list': stock_obj,
                                       'offer_price': Decimal(row[4]).quantize(Decimal('1.00')),
                                       'quantity_per_bag': row[5] / stock_obj.bags_quantity,
                                       'limit': row[6]}

                    stock_item = StockListItemSerializer(data_stock_item)
                    stock_item.get_or_create(data=data_stock_item)
                    continue

                stock_item = StockListItemSerializer(instance)
                stock_item.update(instance=instance, validated_data=row)
            # удаление временного файла
            os.remove(file_name)
            # уведомление staff о полной загрузке сток листа
            if not result_list:
                stock_list_update.send(sender=self.__class__,
                                       user=User.objects.filter(type='staff').first(),
                                       obj=stock_obj,
                                       request_data={'status': 'items uploaded'})
                return JsonResponse({'stock list status': 'all items successfully uploaded'})
            # ответ если не все было загружено
            return JsonResponse({'status': f'added {stock_obj.id}',
                                 'items': result_list})

        # загрузка цен и перевода для staff
        elif request.user.type == 'staff':
            # поиск необходимого сток листа
            stock_obj = StockList.objects.filter(id=pk,
                                                 status='uploaded').first()
            if not stock_obj:
                return JsonResponse({'error': 'no this stock'})

            # создание временного файла
            ssl._create_default_https_context = ssl._create_unverified_context
            file_name = f'stock_list_prices_{date.today()}_{stock_obj.company.id}.xls'
            urllib.request.urlretrieve(url, file_name)
            wb = xlrd.open_workbook(file_name)
            sheet = wb.sheet_by_index(0)
            # Проверка шапки файла на соответствие
            if sheet.row_values(0) != ['code', 'russian_name', 'sale_price']:
                os.remove(file_name) # удаление временного файла
                return JsonResponse({'error': 'incorrect fields in file'})

            result_list = {} # список ошибок
            for rownum in range(1, sheet.nrows):
                row = sheet.row_values(rownum)
                result = StockListItem.objects.select_related('item').filter(stock_list=pk,
                                                                             item__code=row[0]).first()
                # проверка наличия заполненности нужных полей в файле и их нахождения в базе
                if not row[2] or not row[1] or not row[0] or not result:
                    if result:
                        result.status = False
                        result.save()
                    result_list[row[0]] = 'not_added'
                    continue
                serializer = StockListItemSerializer(result)
                serializer.get_or_update(obj=result,
                                         data={'russian_name': row[1], 'sale_price': row[2]})
            os.remove(file_name)
            if not result_list:
                return JsonResponse({'stock list status': 'all items successfully uploaded'})
            return JsonResponse(result_list)
        return JsonResponse({'error': 'no rights'})


class Stock(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, pk=None, *args, **kwargs):
        # получение стоков покупателем: только активные стоки
        if request.user.type == 'cnee':
            obj = StockList.objects.filter(status='offered').all()
            if pk:
                obj = StockList.objects.filter(status='offered', id=pk)
                if not obj:
                    return JsonResponse({'incorrect id': f'{pk}'})
            # используется сериализатор для покупателей
            serializer = GetStockCneeSerializer(obj, many=True)
            return Response(serializer.data)
        # получение стоков поставщиком - только стоки принадлежащие поставщику
        elif request.user.type == 'shpr':
            obj = StockList.objects.select_related('company').filter(company__user=request.user)
            if pk:
                obj = StockList.objects.select_related('company').filter(company__user=request.user, id=pk)
                if not obj:
                    return JsonResponse({'incorrect id': f'{pk}'})
            # используется сериализатор для поставщиков
            serializer = GetStockShprSerizlier(obj, many=True)
            return Response(serializer.data)
        # получение стоков пользователем поставщик/покупатель, отбираются стоки активные и принадлежащие поставщику
        elif request.user.type == 'shpr/cnee':
            # происходит отбор всех предложенных стоков и стоков принадлежащих поставщику
            obj = StockList.objects.select_related('company').filter(Q(company__user=request.user) | Q(status='offered'))
            if pk:
                # если пк = компания пользователя - выгрузка происходит по сериализатору поставщика
                obj = StockList.objects.select_related('company').filter(company__user=request.user, id=pk)
                if obj:
                    serializer = GetStockShprSerizlier(obj, many=True)
                    return Response(serializer.data)
                # если пк - не компания поставщика, но активный сток выгрузка происходит как покупателю
                obj = StockList.objects.select_related('company').filter(id=pk, status='offered')
                if obj:
                    return Response(GetStockCneeSerializer(obj, many=True).data)
                return JsonResponse({'incorrect id': f'{pk}'})
            # все стоки выгружаются как покупателю
            serializer = GetStockCneeSerializer(obj, many=True)
            return Response(serializer.data)
        # получение сток листов работником
        elif request.user.type == 'staff':
            obj = StockList.objects.all()
            if pk:
                obj = StockList.objects.filter(id=pk)
            # более развернутый сериализатор
            serializer = GetStockStaffSerializator(obj, many=True)
            return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        # размещать стоки могут только shpr и shpr/cnee
        if request.user.type not in ['shpr', 'shpr/cnee']:
            return JsonResponse({'error': 'incorrect method'})
        stock_list = StockListCreateSerializer(data=request.data, context={'request': request})
        # проверка компании и адреса отправления
        stock_list.is_valid(raise_exception=True)

        stock = stock_list.get_or_create(validated_data=request.data)
        # уведомление пользователя staff об новом сток листе
        new_stock_list.send(sender=self.__class__, nsl=stock)
        return Response({'status': 'successful',
                         'stock_id': f'{stock.id}'})

    def put(self, request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'No pk'})
        # обновление сток листа поставщиками.
        if request.user.type in ['shpr', 'shpr/cnee']:
            instance = StockList.objects.select_related('company', 'stock_type').filter(id=pk,
                                                                                        company__user=request.user).first()
            if not instance:
                return JsonResponse({'incorrect id': f'{pk}'})
            stock = StockUpdateShprSerializer(context={"request": request}, data=request.data)
            stock.is_valid(raise_exception=True)
            stock = stock.update(instance=instance, validated_data=request.data,)
            # отправка уведомления staff об изменениях
            stock_list_update.send(sender=self.__class__,
                                   user=User.objects.filter(type='staff').first(),
                                   obj=stock,
                                   request_data=request.data)
            return JsonResponse({'status': ' successful',
                                 'stock_id': f'{stock.id} updated'})
        # обновление сток листа пользователем staff
        elif request.user.type == 'staff':
            instance = StockList.objects.filter(id=pk).first()
            if not instance:
                return JsonResponse({'incorrect id': f'{pk}'})
            stock = StockUpdateStaffSerializer(data=request.data)
            stock.is_valid(raise_exception=True)
            stock = stock.update(instance=instance, validated_data=request.data)
            # отправка сообщения об изменении поставщику разместившему сток
            stock_list_update.send(sender=self.__class__, user=instance.company.user, obj=stock,
                                   request_data=request.data)
            return JsonResponse({'status': ' successful',
                                 'stock_id': f'{stock.id} updated'})
        return JsonResponse({'Put method': 'not allowed'})

    def delete(self, request, pk=None, *args, **kwargs):
        # Доступно только staff и поставщикам
        if not pk:
            return JsonResponse({'error': 'No pk'})
        # удаление стока - изменение его статуса на closed
        elif request.user.type in ['shpr', 'shpr/cnee']:
            # проверка принадлежности стока поставщику
            obj = StockList.objects.select_related('company').filter(id=pk, company__user=request.user).first()
            if not obj:
                return JsonResponse({'incorrect id': f'{pk}'})
            obj.status = 'closed'
            obj.save()
            # информирование стафф об размещении нового сток листа
            stock_list_update.send(sender=self.__class__,
                                   user=User.objects.filter(type='staff').first(),
                                   obj=obj,
                                   request_data=[]
                                   )
            return JsonResponse({'status': ' successful',
                                 'stock_id': f'{obj.id} deleted'})
        elif request.user.type == 'staff':
            obj = StockList.objects.select_related('company').filter(id=pk).first()
            if not obj:
                return JsonResponse({'incorrect id': f'{pk}'})
            obj.status = 'closed'
            obj.save()
            # информирование поставщика об изменении его сток листа
            stock_list_update.send(sender=self.__class__,
                                   user=obj.company.user,
                                   obj=obj,
                                   request_data=[]
                                   )
            return JsonResponse({'status': ' successful',
                                 'stock_id': f'{obj.id} deleted'})

        return JsonResponse({'Put method': 'not allowed'})


class UserShipTo(APIView):
    permission_classes = (IsCneeShpr,)
    """
    Получение всего списка адресов или одного по ид
    """

    def get(self, request, pk=None, *args, **kwargs):
        com = ShipAddresses.objects.select_related('company').filter(company__user=request.user.id,
                                                                     active=True)
        if pk:
            com = ShipAddresses.objects.select_related('company').filter(company__user=request.user.id,
                                                                         id=pk,
                                                                         active=True)
        if com:
            serializer = ShipToSerializer(com, many=True)
            return Response(serializer.data)
        return JsonResponse({'error': 'no rights'})

    """
    Размещение нового адреса
    """

    def post(self, request, *args, **kwargs):
        serializer = ShipAddressesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = CompanyDetails.objects.filter(id=request.data['company'], user=request.user.id)
        # проверка компании на соответствие пользователю
        if not company:
            return JsonResponse({'error': f'company with id {request.data["company"]} belongs to other user'})
        serializer.create(validated_data=request.data)
        return JsonResponse({'created': f'object{serializer}'})

    """
    Можно обновлять удаленный ранее объект с помощью поиска по пк, он будет возвращен из удаленных.
    """

    def put(self, request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'No pk'})
        try:
            # проверка на принадлежность компании пользователю
            if CompanyDetails.objects.get(id=request.data['company']).user.id != request.user.id:
                return JsonResponse({'error': 'incorrect company data'})
            # проверка на ид адреса
            instance = ShipAddresses.objects.get(id=pk)
        except:
            return JsonResponse({'error': 'object doesnt not exists'})
        serializer = ShipAddressesUpdateSerializer(data=request.data, instance=instance, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return JsonResponse({'status': f'item with pk{pk} updated'})

    """
    Фактическое удаление не предусмотренно т.к. адрес мог ранее использоваться, меняется только статус.
    """

    def delete(self, request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'need pk'})
        com = ShipAddresses.objects.select_related('company').filter(company__user=request.user.id,
                                                                     id=pk,
                                                                     active=True).first()
        if not com:
            return JsonResponse({'error': 'no item with this pk or have no rights'})
        com.active = False
        com.save()
        return JsonResponse({'status': 'deleted', 'object': f'{ShipToSerializer(com).data}'})


class UserCompanies(APIView):
    permission_classes = (IsCneeShpr,)
    """
    Работа с компаниями покупателя и поставщика, один пользователь может представлять несколько компаний,
    вне зависимости от того поставщик он или покупатель.
    Также пользователь может быть одновременно поставщиком и покупателем.
    """

    def get(self, request, pk=None, *args, **kwargs):
        company_list = CompanyDetails.objects.select_related('city', 'user').filter(user=request.user.id,
                                                                                    active=True)
        if pk:
            company_list = CompanyDetails.objects.select_related('city', 'user').filter(user=request.user.id,
                                                                                        id=pk,
                                                                                        active=True)
        if not company_list:
            return JsonResponse({'error': 'no item with this pk or have no rights'})
        serializer = CompanyDetailsSerializer(data=company_list, many=True)
        serializer.is_valid()
        return Response(serializer.data)

    """
    Добавление компаний к пользователю подразумевает только добавление одной компании за раз, также
    происходит поиск совпадений по бд (если пользователь удалил а потом пытается создать заново), если 
    находит ранее удаленную запись - меняет ее статус и статус всех адресов, которые были связаны с ней.
    П.С. - лишнее усложнение
    """

    def post(self, request, *args, **kwargs):
        if not {'name', 'city', 'street', 'bld', 'bank_details'}.issubset(request.data):
            return JsonResponse({'status': 'incorrect fields'})
        request.data['company_type'] = request.user.type
        request.data['user'] = request.user.id
        serializer = CompanyDetailsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.get_or_create(validated_data=request.data)
        return JsonResponse({'status': serializer.data})

    """
    Изменение записи - происходит поиск по бд определенной записи с отсевом по авторству.
    если пользователь хочет изменить ранее удаленную запись то она восстанавливается и восстанавливаются все 
    адреса доставки связанные с ней. П.С. совершенно не логично, как он может изменить то, чего не видит... 
    """

    def put(self, request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'no pk'})
        instance = CompanyDetails.objects.filter(id=pk, user=request.user.id).first()
        if not instance:
            return JsonResponse({'error': 'no item with this pk or have no rights'})
        request.data['company_type'] = request.user.type
        request.data['user'] = request.user.id
        serializer = CompanyDetailsUpdateSerializer(data=request.data, instance=instance)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # происходит перебор адресов доставки по данной компании и их восстановление
        ship_to = ShipAddresses.objects.filter(company=pk).all()
        if ship_to:
            for element in ship_to:
                element.active = True
                element.save()
        return JsonResponse({'status': f'item with pk{pk} updated'})

    """
    При удалении компании, фактического удаления не происходит, меняется лишь статус отображения, как для нее,
    так и для всех адресов доставки используемых в данной компании
    """

    def delete(self, request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'no PK'})
        company = CompanyDetails.objects.filter(id=pk, user_id=request.user.id).first()
        if not company:
            return JsonResponse({'error': 'no item with this pk or have no rights'})
        company.active = False
        company.save()
        addr = ShipAddresses.objects.filter(company_id=company.id).all()
        for one in addr:
            one.active = False
            one.save()
        return JsonResponse({'status': f'{pk} deleted'})


class SetStockTypes(APIView):
    permission_classes = (IsStaff,)
    """
    Класс загрузки типов сток листов в дб и получения их списка, осуществляется только пользователями группы staff
    """

    def post(self, request, *args, **kwargs):
        if {'stock_types'}.issubset(request.data):
            for element in request.data['stock_types']:
                StockType.objects.get_or_create(name=element['name'].capitalize())
            return JsonResponse({'status': 'stock_types finished'})

    def get(self, request, *args, **kwargs):
        obj = StockType.objects.all()
        serializer = StockTypeSerializer(obj, many=True)
        return Response(serializer.data)

    """
    удаление не предусматривается
    """


class SetFreightRates(APIView):
    permission_classes = (IsStaff,)
    """"
    Загрузка значений стоимости фрахта доступно только пользователям группы staff
    Загрузка возможна только по ссылке с файлом формата xls(не XLSX)
    """

    def post(self, request, *args, **kwargs):
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
        Предполагается, что файл всегда одного вида, меняется лишь количество строк 
        Всегда происходит поиск совпадений и их обновление. 
        В перспективе проще сделать сразу загрузку всех городов мира. с сортировкой по странам - упростит код и логику
         
        """
        for rownum in range(1, sheet.nrows):  # предполагается, что в файле первая строка - заголовок
            row = sheet.row_values(rownum)
            city, _ = City.objects.get_or_create(name=row[1].capitalize(), state_id=state.id)
            FreightRates.objects.update_or_create(POL=row[0], city_id=city.id, price=row[2], minimal_weight=row[3])

        return JsonResponse({'stat': 'ok'})

    """ 
    Получение информации по стоимостям фрахта для всех городов по названию страны
     или для определенного города по его названию
    """

    def get(self, request, pk=None, *args, **kwargs):
        city_list = City.objects.all()
        if pk:
            city_list = City.objects.filter(id=pk)
            if not city_list:
                return JsonResponse({'error': 'no item with this pk or have no rights'})
        return Response(CityFreightSerializer(city_list, many=True).data)

    """
    Удаление не предусмотрено
    """


class UploadStateCity(APIView):
    permission_classes = (IsStaff,)
    """ Внесение в дб информации по странам и городам """

    def post(self, request, *args, **kwargs):
        if {'state'}.issubset(request.data):
            for state in request.data['state']:
                obj, _ = State.objects.get_or_create(name=state['name'].capitalize())
                for element in state['cities']:
                    City.objects.get_or_create(name=element['name'].capitalize(), state_id=obj.id)
            return JsonResponse({'status': 'State and cities filled successfully'})
        return JsonResponse({"status": "incorrect fields"})

    """ 
    Получение информации о городах по ид страны или полная выгрузка
    """

    def get(self, request, pk=None, *args, **kwargs):
        query_set = State.objects.all()
        if pk:
            query_set = State.objects.filter(id=pk).all()
            if not query_set:
                return JsonResponse({'error': 'no item with this pk or have no rights'})
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
    permission_classes = (IsAuthenticated,)
    """
    Класс для работы данными пользователя
    """

    # получить данные
    def get(self, request, *args, **kwargs):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    # Редактирование методом POST
    def post(self, request, *args, **kwargs):
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


