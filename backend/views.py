import os
import ssl
import urllib.request
import xlrd

from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from .tasks import send_email
from datetime import date, timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_list_or_404
from rest_condition import And, Or
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from backend.models import User, State, ConfirmEmailToken, City, FreightRates, StockType, CompanyDetails, \
    ShipAddresses, StockList, StockListItem, Order, OrderedItems, Item, FreightRatesSet
from backend.permissions import IsStaff, IsCneeShpr, IsAuthenticated, IsShprorCnShpr, IsCnee
from backend.serializers import StateSerializer, UserSerializer, StockTypeSerializer, \
    CompanyDetailsSerializer, ShipToSerializer, CompanyDetailsUpdateSerializer, ShipAddressesUpdateSerializer, \
    ShipAddressesSerializer, StockListCreateSerializer, OrderSerializer, \
    GetStockCneeSerializer, GetStockShprSerizlier, GetStockStaffSerializator, StockUpdateShprSerializer, \
    StockUpdateStaffSerializer, GetStockItemsSerializer, FreightRatesSerializer, FreightRateSetSerializer, \
    ItemsCheckSerializer, ItemUpdateSerializer, StockItemUpdateSerializer, GetOrdersShpr, GetOrdersCnee, \
    GetOrdersStaff


class OrderList(ListAPIView):
    """ Получение списка заказов по ид сток листа, разные формы в зависимости от типа пользователя"""
    permission_classes = [Or(And(IsShprorCnShpr, ), And(IsStaff), And(IsCnee), )]
    throttle_classes = [UserRateThrottle]
    def get(self, request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'No pk'})
        if request.user.type == 'cnee':
            obj = get_object_or_404(Order, stock_list=pk, user=request.user)
            serializer = GetOrdersCnee(obj)
            return Response(serializer.data)
        if request.user.type == 'shpr':
            obj = get_object_or_404(StockList.objects.select_related('company'), id=pk, company__user=request.user)
            serializer = GetOrdersShpr(obj)
            return Response(serializer.data)
        if request.user.type == 'shpr/cnee':
            obj = get_list_or_404(Order.objects.select_related('stock_list', 'stock_list__company__user'),
                                  stock_list=pk)
            if obj[0].stock_list.company.user == request.user:
                obj = get_object_or_404(StockList.objects.select_related('company'), id=pk, company__user=request.user)
                serializer = GetOrdersShpr(obj)
            else:
                obj1 = get_object_or_404(Order, stock_list=pk, user=request.user)
                serializer = GetOrdersCnee(obj1)
            return Response(serializer.data)
        if request.user.type == 'staff':
            obj = get_object_or_404(StockList, id=pk)
            serializer = GetOrdersStaff(obj)
            return Response(serializer.data)


class Orders(APIView):
    """ Получение заказов по ид """
    permission_classes = [Or(And(IsCnee, ), And(IsStaff, ), And(IsShprorCnShpr, ))]

    def get(self, request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'No pk'})
        order = None
        user_type = None

        if request.user.type == 'cnee':
            order = get_object_or_404(Order.objects.select_related('stock_list'),
                                      id=pk,
                                      user=request.user.id)
            user_type = request.user.type
        elif request.user.type == 'staff':
            order = get_object_or_404(Order.objects.select_related('stock_list'),
                                      id=pk)
            user_type = request.user.type
        elif request.user.type == 'shpr':
            order = get_object_or_404(Order.objects.select_related('stock_list__company'),
                                      id=pk,
                                      stock_list__company__user=request.user)
            user_type = request.user.type
        elif request.user.type == 'shpr/cnee':
            # Добработать получение заказа по ид поставщиком/покупателем
            order = get_object_or_404(Order.objects.select_related('stock_list__company'), id=pk)
            if order.stock_list.company.user == request.user:
                user_type = 'shpr'
            elif order.user == request.user:
                user_type = 'cnee'
            else:
                return JsonResponse({'incorrect': 'id'})
        serializer = OrderSerializer(order, context={'request': user_type})
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        """ Создание заказа """
        # проверка на актуальность сток листа
        obj = get_object_or_404(StockList.objects.select_related('company__user'), id=request.data['stock_list'], status='offered')
        # проверка принадлежности сток листа, нельзя заказать по своему сток листу
        if obj.company.user == request.user:
            return JsonResponse({'error': 'can not order from your stocklist'})

        if request.user.type == 'shpr':
            return JsonResponse({'error': 'shipper can not make an orders'})
        # проверка входящего джсона

        if not {'items', 'ship_to', 'stock_list'}.issubset(request.data) or not isinstance(request.data['items'], list):
            return JsonResponse({'error': 'incorrect fields'})
        ItemsCheckSerializer(data=request.data['items'], many=True).is_valid(raise_exception=True)
        request.data['stock_list'] = obj
        request.data['user'] = request.user


        # проверка адреса получателя на принадлежность пользователю
        request.data['ship_to'] = get_object_or_404(ShipAddresses.objects.select_related('company'),
                                                    id=request.data['ship_to'],
                                                    company__user=request.user)

        # создание списка ошибок

        check = {i['id']: i['bags'] for i in request.data['items']}  # создание словаря
        # получение из бд заказанных позиций
        item_obj = {m: list(m.ordereditems_set.all()) for m in
                    get_list_or_404(
                        StockListItem.objects.prefetch_related(Prefetch('ordereditems_set',
                                                                        queryset=OrderedItems.objects.filter(
                                                                            status=True))),
                        id__in=list(check.keys()),
                        stock_list=obj,
                        status=True)}
        # создание списка ошибок
        errors_list = []
        # проверка на достаточность пакетов в заказе
        if sum(check.values()) % request.data['stock_list'].bags_quantity != 0:
            errors_list.append({'error': 'incorrect bags quantity'})
        #  Проверка заказываемых позиций на доступность в стоке P.S. можно изменить перебор на сравнение множеств
        id_s = [i.id for i in item_obj.keys()]
        for item in check.keys():
            if item not in id_s:
                errors_list.append({'error': f'incorrect item id: {item}'})
        # проверка достаточности количеств у поставщика
        for key, value in item_obj.items():
            if sum(map(lambda x: x.bags * x.stock_list_item.quantity_per_bag, value)) > key.limit != 0:
                errors_list.append({'status': f'not enough on stock for item  with id: {key.id}'})
        # проверка на наличие сделанного ранее заказа
        if Order.objects.filter(status__in=['Received', 'Confirmed', 'Updated', 'In process', ],
                                user=request.user,
                                stock_list=obj).first():
            errors_list.append({'error': 'this order already in'})

        if errors_list:
            return JsonResponse({'errors': errors_list})
        # создание заказа
        order = Order.objects.create(user=request.data['user'],
                                     ship_to=request.data['ship_to'],
                                     stock_list=obj,
                                     status='Received',
                                     shipment_date=obj.shipment_date)
        # создание позиций заказа
        bulk_list_create = []
        for item in item_obj:
            bags = check[item.id]
            bulk_list_create.append(OrderedItems(bags=bags,
                                                 stock_list_item=item,
                                                 order=order))
        # Булки для добавления и обновления
        OrderedItems.objects.bulk_create(bulk_list_create)
        # фиксация стоимости фрахта
        if order.ship_to.transport_type == 'Air':
            fr_rt_obj = FreightRates.objects.filter(city_id=order.ship_to.city_id).order_by('price').first()
            fr_data = {'price': fr_rt_obj.price,
                       'minimal_weight': fr_rt_obj.minimal_weight,
                       'order': order,
                       'ship_to': order.ship_to}
            frt, _ = FreightRatesSet.objects.get_or_create(**fr_data)

        send_email.delay(cnee=User.objects.filter(type='staff').first().email,
                         sndr=settings.EMAIL_HOST_USER,
                         text=f'Ваш заказ получен',
                         sbj=f"Новый заказ # {order.id}")
        send_email.delay(cnee=request.user.email,
                         sndr=settings.EMAIL_HOST_USER,
                         text=f'Ваш заказ получен',
                         sbj=f"Ваш заказ получен # {order.id}")

        return JsonResponse({'status': 'successful',
                             'order_id': order.id})

    def put(self, request, pk=None, *args, **kwargs):
        """ Изменение заказа """
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
            send_email.delay(cnee=instance.user.email,
                             sndr=settings.EMAIL_HOST_USER,
                             text=f'Статус заказа изменен: {instance.status}',
                             sbj=f"Обновление статуса заказа # {pk}")
            return JsonResponse({'status': 'successful', f'order {pk}': 'updated'})
        # пользователь (cnee или shpr/cnee) может изменять только ship-to,
        # статус заказа меняется на updated автоматически
        if request.user.type in ['cnee', 'shpr/cnee']:
            if not {'ship_to'}.issubset(request.data):
                return JsonResponse({'error': 'need to fill ship_to id'})
            instance = Order.objects.select_related('ship_to').filter(id=pk, user=request.user).first()
            if not instance:
                return JsonResponse({'error': 'incorrect pk or order not belongs to u'})
            request.data['ship_to'] = ShipAddresses.objects.select_related('company').filter(
                company__user=request.user.id,
                id=request.data['ship_to']).first()
            if not request.data['ship_to']:
                return JsonResponse({'error': f'incorrect ship_to id'})
            request.data['status'] = 'Updated'
            serializer = OrderSerializer(request.data)
            serializer.update(validated_data=request.data, instance=instance)
            frt_obj = Order.objects.select_related('ship_to').filter(id=pk, ship_to__transport_type='Air').first()
            if frt_obj:
                fr_rt_obj = FreightRates.objects.filter(city_id=frt_obj.ship_to.city_id).order_by('price').first()
                fr_data = {'price': fr_rt_obj.price,
                           'minimal_weight': fr_rt_obj.minimal_weight,
                           'order': frt_obj,
                           'ship_to': frt_obj.ship_to}
                serializer = FreightRateSetSerializer(fr_data)
                serializer.get_or_create(data=fr_data)
            send_email.delay(cnee=User.objects.filter(type='staff').first().email,
                             sndr=settings.EMAIL_HOST_USER,
                             text=f'Статус заказа изменен: {instance.status}',
                             sbj=f"Обновление статуса заказа # {pk}")
            return JsonResponse({'ok': 'finished'})

    def delete(self, request, pk=None, *args, **kwargs):
        """ Удаление заказа """
        if not pk:
            return JsonResponse({'error': 'No pk'})
        if request.user.type in ['cnee', 'shpr/cnee']:
            #  проверка принадлежности заказа и возможности его удаления (уже отправленные заказы нельзя удалить)
            obj = get_list_or_404(OrderedItems.objects.select_related('order', 'stock_list_item', 'order__stock_list'),
                                  order=pk,
                                  order__user=request.user)
            if obj[1].order.status == "Deleted":
                return JsonResponse({'error': f'order {obj[0].order.id} is already deleted'})
            # проверка временных рамок для удаления (не позднее чем за 2 дня до даты поставки)
            if (obj[1].order.stock_list.shipment_date - timedelta(days=2)) < date.today():
                return JsonResponse({'error': 'can delete not more than 2 days before shipment date'})
            for element in obj:  # use Bulk update
                element.order.status = 'Deleted'
                element.stock_list_item.save()
                element.status = False
                element.save()
                element.order.save()

        send_email.delay(cnee=User.objects.filter(type='staff').first().email,
                         sndr=settings.EMAIL_HOST_USER,
                         text=f'Статус заказа изменен: Deleted',
                         sbj=f"Обновление статуса заказа # {pk}")
        return JsonResponse({'end': 'delete'})


class GetStockItems(APIView):
    """ Получение позиций из сток листа """
    permission_classes = (IsAuthenticated,)
    throttle_classes = [UserRateThrottle]

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


class StockItemUpdate(APIView):
    """ Обновление позиций сток листа"""
    permission_classes = [Or(And(IsShprorCnShpr, ), And(IsStaff), )]

    def post(self, request, pk=None, *args, **kwargs):
        """ Размещение новой позиции к сток-листу поставщиком
            как пк используется ид сток листа """

        if request.user.type in ['shpr', 'shpr/cnee']:
            stock_list = get_object_or_404(StockList.objects.select_related('company'),
                                           id=pk,
                                           company__user=request.user,
                                           status__in=['offered', 'received', 'updated'])
            item = ItemUpdateSerializer(data=request.data)
            item.is_valid(raise_exception=True)
            item_obj = Item.objects.filter(company=stock_list.company, code=request.data['code']).first()
            # если позиция не найдена - то она создается, также, как и создается позиция к сток листу
            if not item_obj:
                item = Item.objects.create(code=request.data['code'],
                                           english_name=request.data['english_name'],
                                           scientific_name=request.data['scientific_name'],
                                           size=request.data['size'],
                                           company=stock_list.company
                                           )
                stock_list_item = StockListItem.objects.create(item=item,
                                                               offer_price=request.data['offer_price'],
                                                               quantity_per_bag=request.data['quantity_per_bag'],
                                                               limit=request.data['limit'],
                                                               stock_list=stock_list)
                # информирование работника об добавлении новой позиции
                send_email.delay(cnee=User.objects.filter(type='staff').first().email,
                                 sndr=settings.EMAIL_HOST_USER,
                                 text=f'В сток лист {stock_list_item.stock_list} добавлена позиция',
                                 sbj=f'Добавление позиции {stock_list_item.id}')
                return Response({'item': stock_list_item.id, 'status': 'created'})
            # если позиция была найдена в бд, то она просто добавляется к сток листу
            stock_list_item = StockListItem.objects.filter(item=item_obj).first()
            if stock_list_item:
                return JsonResponse(
                    {f'item with id {stock_list_item.id}': 'is already in stock list, use PUT METHOD to change it'})
            stock_list_item = StockListItem.objects.create(item=item_obj,
                                                           offer_price=request.data['offer_price'],
                                                           quantity_per_bag=request.data['quantity_per_bag'],
                                                           limit=request.data['limit'],
                                                           stock_list=stock_list)
            send_email.delay(cnee=User.objects.filter(type='staff').first().email,
                             sndr=settings.EMAIL_HOST_USER,
                             text=f'В сток лист {stock_list_item.stock_list} добавлена позиция',
                             sbj=f'Добавление позиции {stock_list_item.id}')
            return Response({'item': stock_list_item.id, 'status': 'created'})

    def put(self, request, pk=None, *args, **kwargs):
        """ Обновление позиций сток листа"""

        if request.user.type == 'staff':
            """ Обновление свежедобавленной или иной позиции активного сток листа пользователем staff 
                может поменять цену продажную, перевод, статус, если нет цены продажной автостатус - false"""
            obj = get_object_or_404(StockListItem.objects.select_related('item', 'stock_list'),
                                    id=pk,
                                    stock_list__status__in=['offered', 'closed', 'uploaded', 'updated'])
            item = StockItemUpdateSerializer(data=request.data)
            item.is_valid(raise_exception=True)
            result = item.update(instance=obj, validated_data=request.data)
            return JsonResponse({f'item {result.id}': f'{result.status, result.sale_price}'})

        if request.user.type in ['shpr', 'shpr/cnee']:
            # если сток лист принадлежит пользователю, если он не deleted или finished, если позиция в стоке
            obj = get_object_or_404(StockListItem.objects.select_related('item',
                                                                         'stock_list'),
                                    id=pk,
                                    stock_list__company__user=request.user,
                                    stock_list__status__in=['offered', 'closed', 'uploaded', 'updated'])
            # получение заказов по позиции из пк
            orders = OrderedItems.objects.select_related('order').filter(stock_list_item=obj, status=True)
            orders_list = []  # список заказов с деталями
            orders_list_for_staff = 'Без заказов'  # исходная переменная для направления информации staff
            bags = 0  # количество пакетов из заказов
            if orders:  # заполнение переменных при наличии заказов
                #  детализация заказов
                orders_list = [[order, order.order.user.email, order.order.created_at, order.bags] for order in orders]
                bags = sum([x[3] for x in orders_list])  # суммирования кол-ва пакетов по заказам
                order_list_for_staff = [order.id for order in orders]

            updated_info = {}  # словарь изменений
            # получение изменяемых данных при их наличии
            new_price = request.data.get('offer_price', obj.offer_price)
            eng_name = request.data.get('english_name', obj.item.english_name)
            sci_name = request.data.get('scientific_name', obj.item.scientific_name)
            size = request.data.get('size', obj.item.size)
            q_p_b = request.data.get('quantity_per_bag', obj.quantity_per_bag)
            limit = request.data.get('limit', obj.limit)

            # сравнение данных
            if new_price != obj.offer_price:
                # изменение цены продажи основываясь на новой цене
                new_price = (round(Decimal(request.data['offer_price']), 2) + (obj.sale_price - obj.offer_price))
                updated_info['sale_price'] = f'{obj.sale_price} -> {new_price}'
                obj.sale_price = new_price
                obj.offer_price = request.data['offer_price']
            if eng_name != obj.item.english_name and eng_name != obj.english_name:
                updated_info['english_name'] = f'{obj.english_name} -> {eng_name}'
                obj.english_name = eng_name
            if sci_name != obj.item.scientific_name and sci_name != obj.scientific_name:
                updated_info['scientific_name'] = f'{obj.scientific_name} -> {sci_name}'
                obj.scientific_name = sci_name
            if size != obj.item.size and size != obj.size:
                updated_info['size'] = f'{obj.size} -> {size}'
                obj.size = size

            counting = 0
            #  работа с лимитами и заказанными позициями -> выявление нехватки при уменьшении количества лимита и/или его создании
            if q_p_b != obj.quantity_per_bag and limit != obj.limit:
                if limit < (q_p_b * bags):
                    counting = int(round(((q_p_b * bags) - limit) / q_p_b, 0))
                updated_info['quantity_per_bag'] = f'{obj.quantity_per_bag} -> {q_p_b}'
                obj.limit = limit
                obj.quantity_per_bag = q_p_b
            elif q_p_b != obj.quantity_per_bag and limit == obj.limit:
                if q_p_b != obj.quantity_per_bag and obj.limit < (q_p_b * bags):
                    counting = int(round(((q_p_b * bags) - obj.limit) / q_p_b, 0))
                updated_info['quantity_per_bag'] = f'{obj.quantity_per_bag} -> {q_p_b}'
                obj.quantity_per_bag = q_p_b
            elif q_p_b == obj.quantity_per_bag and limit != obj.limit:
                if limit != obj.limit and limit < (obj.quantity_per_bag * bags):
                    counting = int(round(((obj.quantity_per_bag * bags) - limit) / obj.quantity_per_bag, 0))
                obj.limit = limit

            #  отправка сообщения staff
            if updated_info:
                obj.status = False
                send_email.delay(cnee=User.objects.filter(type='staff').first().email,
                                 sndr=settings.EMAIL_HOST_USER,
                                 text=f'Позиция {obj.id, obj.english_name, obj.scientific_name},'
                                      f' {updated_info}'
                                      f' до {obj.stock_list.orders_till_date}',
                                 sbj=f'Обновление статуса заказа orders_list_for_staff')

            obj.save()
            #  проход по заказам и определение темы сообщения для отправки клиентам
            if orders:
                list_for_bulk = []
                for order in sorted(orders_list, key=lambda x: x[2], reverse=True):
                    # удаление позиций сверх лимита
                    if counting > 0:
                        order[0].status = False
                        list_for_bulk.append(order[0])
                        order.append(
                            f'Отсутствует на складе, вам нужно дозаказать другую позицию в количестве {order[3]}')
                        counting -= order[3]

                    else:
                        order.append(f'изменена : {updated_info}')
                # групповое обоновление заказанных позиций
                OrderedItems.objects.bulk_update(list_for_bulk, fields=('status',))
                # отправка писем клиентам (для ускорения можно сгруппировать по теме и отправить в скрытых копиях)
                for element in orders_list:
                    send_email.delay(cnee=element[1],
                                     sndr=settings.EMAIL_HOST_USER,
                                     text=f'Позиция {obj.id, obj.english_name, obj.scientific_name},'
                                          f' {element[4]}'
                                          f' до {obj.stock_list.orders_till_date}',
                                     sbj=f'Обновление статуса заказа {element[0].order.id}')

            return JsonResponse({'item': f'{obj.id}', 'status': 'updated'})

    def delete(self, request, pk=None, *args, **kwargs):
        pass


class StockItemsUpload(APIView):
    """ Загрузка эксель файлов с позициями для сток листов """
    permission_classes = (IsAuthenticated,)

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
            # True то любые изменения через view StockItemsUpdate
            if StockListItem.objects.filter(stock_list=pk, ).first():
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
            items_dict = {}  # создание словаря позиций
            items_list = []  # создание списка всех кодов
            stock_item_bulk = []  # создание списка булк для загрузки в бд
            for rownum in range(1, sheet.nrows):
                row = sheet.row_values(rownum)
                # получение/ создание позиции
                if not all(row[i] for i in range(6)):  # проверка заполненности строки
                    result_list[f'row_{rownum}'] = {'code': row[0],
                                                    'english_name': row[1],
                                                    'scientific_name': row[2],
                                                    'size': row[3],
                                                    'offer_price': row[4],
                                                    'limit': row[5]}
                    # остановка процесса в случае если много пустых ячеек - нужно для длинных листов
                    if len(result_list) > 20:
                        break
                    continue
                # получение лимитов, пустые ячейки из excel выводятся в виде пустой строки
                if row[6] == '':
                    limit = 0
                else:
                    limit = row[6]
                # добавление позиции в словарь позиций
                items_dict[row[0]] = {'english_name': row[1],
                                      'scientific_name': row[2],
                                      'size': row[3],
                                      'company': stock_obj.company,
                                      'offer_price': Decimal(row[4]).quantize(Decimal('1.00')),
                                      'quantity_per_bag': row[5] / stock_obj.bags_quantity,
                                      'limit': limit}
                # добавление кода позиции в список позиций (для предотвращения дублей)
                items_list.append(row[0])
            # получение позиций из бд по сформированному списку
            items_qs = Item.objects.select_related('company').filter(code__in=items_dict.keys(),
                                                                     company__user=request.user)
            # формирования списка кодов из queryset
            qs_codes = [str(i.code) for i in items_qs]
            # создание списка Item, которых нет в базе
            difference = set(qs_codes) ^ set(items_list)
            #  добавление новых позиций если они есть
            if len(difference) != 0:
                bulk_list_items = []
                for element in difference:
                    bulk_list_items.append(Item(code=element,
                                                scientific_name=items_dict[element]['scientific_name'],
                                                english_name=items_dict[element]['english_name'],
                                                size=items_dict[element]['size'],
                                                company=stock_obj.company,
                                                ))
                result = Item.objects.bulk_create(bulk_list_items)
                # проход по новым позициям для добавления их в список булк для создания StokListItem
                for element in result:
                    bulk = StockListItem(offer_price=items_dict[element.code]['offer_price'],
                                         quantity_per_bag=items_dict[element.code]['quantity_per_bag'],
                                         limit=items_dict[element.code]['limit'],
                                         item=element,
                                         stock_list=stock_obj)
                    stock_item_bulk.append(bulk)
            # проход по найденным позициям в бд для добавления их в список булк для создания StokListItem
            for element in items_qs:
                bulk = StockListItem(offer_price=items_dict[element.code]['offer_price'],
                                     quantity_per_bag=items_dict[element.code]['quantity_per_bag'],
                                     limit=items_dict[element.code]['limit'],
                                     item=element,
                                     stock_list=stock_obj)
                stock_item_bulk.append(bulk)
            # Создание через булк всех позиций
            StockListItem.objects.bulk_create(stock_item_bulk)
            # удаление временного файла
            os.remove(file_name)
            # уведомление staff о полной загрузке сток листа
            send_email.delay(cnee=User.objects.filter(type='staff').first().email,
                             sndr=settings.EMAIL_HOST_USER,
                             text='status: items uploaded',
                             sbj=f"Сток лист от {stock_obj.company.name} обновился")
            return JsonResponse({'status': f'added {stock_obj.id}',
                                 'errors': result_list})

        # загрузка цен и перевода для staff
        elif request.user.type == 'staff':
            # поиск необходимого сток листа
            stock_obj = get_object_or_404(StockList, id=pk, status='uploaded')
            # создание временного файла
            ssl._create_default_https_context = ssl._create_unverified_context
            file_name = f'stock_list_prices_{date.today()}_{stock_obj.company.id}.xls'
            urllib.request.urlretrieve(url, file_name)
            wb = xlrd.open_workbook(file_name)
            sheet = wb.sheet_by_index(0)
            # Проверка шапки файла на соответствие
            if sheet.row_values(0) != ['code', 'russian_name', 'sale_price']:
                os.remove(file_name)  # удаление временного файла
                return JsonResponse({'error': 'incorrect fields in file'})
            # создания словаря с ошибками по группам
            result_list = {'excel': [], 'db_no_russian_name': [], 'db_no_sale_price': []}  # список ошибок
            items_dict = {}  # словарь с позициями
            # проход по загружаемому файлу
            for rownum in range(1, sheet.nrows):
                row = sheet.row_values(rownum)
                if not all(row[i] for i in range(3)):  # проверка заполненности строки
                    result_list['excel'].append({f'row_{rownum}': {'code': row[0],
                                                                   'russian_name': row[1],
                                                                   'sale_price': row[2]}})
                    continue
                items_dict[row[0]] = {'russian_name': row[1],
                                      'sale_price': row[2]}
            # обновление позиций, которые без перевода
            items_qs = Item.objects.select_related('company').filter(company=stock_obj.company,
                                                                     russian_name__in=['', ' '])

            for element in items_qs:
                russian_name = items_dict.get(f'{element.code}')
                if not russian_name:
                    result_list['db_no_russian_name'].append({element.code: {'id': element.id,
                                                                             'russian_name': element.russian_name}})
                    continue
                element.russian_name = items_dict[element.code]['russian_name']
            Item.objects.bulk_update(items_qs, fields=('russian_name',))
            stock_items_qs = StockListItem.objects.select_related('item').filter(stock_list=stock_obj, )
            for element in stock_items_qs:
                sale_price = items_dict.get(f'{element.item.code}')
                if not sale_price:
                    element.status = False
                    result_list['db_no_sale_price'].append({element.item.code: {'id': element.item.id,
                                                                                'sale_price': '',
                                                                                'status': False}})
                    continue
                element.sale_price = items_dict[element.item.code]['sale_price']
                if not element.item.russian_name or element.item.russian_name == ' ':
                    result_list[element.code] = '123'
                    element.status = False
                    continue
                element.status = True
            StockListItem.objects.bulk_update(stock_items_qs, fields=('sale_price', 'status',))

            os.remove(file_name)
            return JsonResponse({'errors': result_list})
        return JsonResponse({'error': 'no rights'})


class Stock(APIView):
    """ создание, получение, изменение, удаление сток листов"""
    permission_classes = (IsAuthenticated,)
    throttle_classes = [UserRateThrottle]

    @staticmethod
    def get(request, pk=None, *args, **kwargs):
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
            obj = StockList.objects.select_related('company').filter(
                Q(company__user=request.user) | Q(status='offered'))
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
        send_email.delay(cnee=User.objects.filter(type='staff').first().email,
                         sndr=settings.EMAIL_HOST_USER,
                         text=f"id: {stock.id=}\n"
                              f"shipment_dat: {stock.shipment_date}\n"
                              f"orders_till_date: {stock.orders_till_date}\n"
                              f"stock_type: {stock.stock_type.name}\n"
                              f"bags_quantity: {stock.bags_quantity}\n"
                              f"box_weight: {stock.box_weight}\n"
                              f"currency_type: {stock.currency_type}\n"
                              f"transport_type: {stock.transport_type}\n",
                         sbj=f"новый сток лист от {stock.company.name}")
        return JsonResponse({'status': 'successful',
                             'stock_id': f'{stock.id}'})

    def put(self, request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'No pk'})
        # Обновление сток листа поставщиками. также можно изменять статус сток листа на closed
        if request.user.type in ['shpr', 'shpr/cnee']:
            instance = StockList.objects.select_related('company',
                                                        'stock_type').filter(id=pk,
                                                                             company__user=request.user).first()
            if not instance:
                return JsonResponse({'incorrect id': f'{pk}'})
            stock = StockUpdateShprSerializer(context={"request": request}, data=request.data)
            stock.is_valid(raise_exception=True)
            stock = stock.update(instance=instance, validated_data=request.data, )
            # отправка уведомления staff об изменениях
            send_email.delay(cnee=User.objects.filter(type='staff').first(),
                             sndr=settings.EMAIL_HOST_USER,
                             text=request.data,
                             sbj=f"Сток лист от {stock.company.name} обновился")
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
            send_email.delay(cnee=instance.company.user.email,
                             sndr=settings.EMAIL_HOST_USER,
                             text=f'{request.data}',
                             sbj=f"Сток лист от {stock.company.name} обновился")
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
            obj.status = 'deleted'
            obj.save()
            # информирование стафф об удалении стока поставщиком
            send_email.delay(cnee=User.objects.filter(type='staff').first(),
                             sndr=settings.EMAIL_HOST_USER,
                             text=[],
                             sbj=f"Статус Сток листа от {obj.company.name} обновился")
            return JsonResponse({'status': ' successful',
                                 'stock_id': f'{obj.id} deleted'})
        elif request.user.type == 'staff':
            obj = StockList.objects.select_related('company').filter(id=pk).first()
            if not obj:
                return JsonResponse({'incorrect id': f'{pk}'})
            obj.status = 'deleted'
            obj.save()
            # информирование поставщика об изменении его сток листа
            send_email.delay(cnee=obj.user.email,
                             sndr=settings.EMAIL_HOST_USER,
                             text=[],
                             sbj=f"Статус Сток листа от {obj.company.name} обновился на {obj.status}")
            return JsonResponse({'status': ' successful',
                                 'stock_id': f'{obj.id} deleted'})

        return JsonResponse({'Put method': 'not allowed'})


class UserShipTo(ListAPIView):
    """ Получение всего списка адресов или одного по ид """
    permission_classes = (IsCneeShpr,)
    throttle_classes = [UserRateThrottle]

    def get(self, request, pk=None, *args, **kwargs):
        obj = ShipAddresses.objects.select_related('company').filter(company__user=request.user.id,
                                                                     active=True,
                                                                     company__active=True)
        if pk:
            obj = ShipAddresses.objects.select_related('company').filter(company__user=request.user.id,
                                                                         id=pk,
                                                                         active=True,
                                                                         company__active=True)
        if obj:
            serializer = ShipToSerializer(obj, many=True)
            return Response(serializer.data)
        return JsonResponse({'error': 'no rights'})

    """
    Размещение нового адреса
    """

    @staticmethod
    def post(request, *args, **kwargs):
        serializer = ShipAddressesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = CompanyDetails.objects.filter(id=request.data['company'], user=request.user.id, active=True).first()
        # проверка компании на соответствие пользователю
        if not company:
            return JsonResponse({'error': 'incorrect company id'})
        result = serializer.get_or_create(validated_data=request.data)
        return JsonResponse({'created': f'ship_to id {result.id}'})

    """
    Можно обновлять удаленный ранее объект с помощью поиска по пк, он будет возвращен из удаленных.
    """

    @staticmethod
    def put(request, pk=None, *args, **kwargs):
        if not pk:
            return JsonResponse({'error': 'No pk'})
        try:
            # проверка на принадлежность компании пользователю
            if not ShipAddresses.objects.select_related('company').filter(company_id=request.data['company'],
                                                                          company__active=True,
                                                                          company__user=request.user,
                                                                          id=pk).first():
                return JsonResponse({'error': 'incorrect company id or ship_to id'})
            # проверка на ид адреса
            instance = ShipAddresses.objects.select_related('company__city').get(id=pk)
        except:
            return JsonResponse({'error': 'object doesnt not exists'})
        serializer = ShipAddressesUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update(instance=instance, validated_data=request.data)
        return JsonResponse({'status': f'item with pk {pk} updated'})

    @staticmethod
    def delete(request, pk=None, *args, **kwargs):
        """ Фактическое удаление не предусмотренно т.к. адрес мог ранее использоваться, меняется только статус. """
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
    throttle_classes = [UserRateThrottle]
    """
    Работа с компаниями покупателя и поставщика, один пользователь может представлять несколько компаний,
    вне зависимости от того поставщик он или покупатель.
    Также пользователь может быть одновременно и поставщиком и покупателем.
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
            FreightRates.objects.update_or_create(POL=row[0],
                                                  city_id=city.id,
                                                  price=Decimal(row[2]),
                                                  minimal_weight=Decimal(row[3]))

        return JsonResponse({'stat': 'ok'})

    """ 
    Получение информации по стоимостям фрахта для всех городов по названию страны
     или для определенного города по его названию
    """

    def get(self, request, pk=None, *args, **kwargs):
        city_list = FreightRates.objects.select_related('city')
        if pk:
            city_list = FreightRates.objects.select_related('city').filter(city_id=pk)
            if not city_list:
                return JsonResponse({'error': 'no item with this pk or have no rights'})
        return Response(FreightRatesSerializer(city_list, many=True).data)

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
                    send_email.delay(cnee=token.user.email,
                                     sndr=settings.EMAIL_HOST_USER,
                                     text=token.key,
                                     sbj=f"Token for {token.user.email}")
                    return JsonResponse({'Status': True, 'Token': token.key})

            return JsonResponse({'Status': False, 'Errors': 'Не удалось авторизовать'})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class AccountDetails(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = [UserRateThrottle]
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
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
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
                # request.data._mutable = True
                request.data.update({})
                user_serializer = UserSerializer(data=request.data)
                if user_serializer.is_valid():
                    # сохраняем пользователя
                    user = user_serializer.save()
                    user.set_password(request.data['password'])
                    user.save()
                    token, _ = ConfirmEmailToken.objects.get_or_create(user_id=user.id)
                    send_email.delay(cnee=token.user.email,
                                     sndr=settings.EMAIL_HOST_USER,
                                     text=token.key,
                                     sbj=f"Password Reset Token for {token.user.email}")
                    return JsonResponse({'Status': True})
                else:
                    return JsonResponse({'Status': False, 'Errors': user_serializer.errors})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class ConfirmAccount(APIView):
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
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
                send_email.delay(cnee=token.user.email,
                                 sndr=settings.EMAIL_HOST_USER,
                                 text=f'email {request.data["email"]} confirmed',
                                 sbj=f'email confirmed {request.data["email"]}')
                return JsonResponse({'Status': True})
            else:
                return JsonResponse({'Status': False, 'Errors': 'Неправильно указан токен или email'})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})
