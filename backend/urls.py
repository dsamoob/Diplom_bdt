from django.template.defaulttags import url
from django.urls import path, include
from django.contrib import admin
import debug_toolbar

from django.conf import settings
from django_rest_passwordreset.views import reset_password_request_token, reset_password_confirm

from backend.views import UploadStateCity, RegisterAccount, LoginAccount, AccountDetails,\
    ConfirmAccount, SetFreightRates, SetStockTypes, UserCompanies, UserShipTo, StockItemsUpload,\
    Orders, Stock, GetStockItems
app_name = 'diplom'


urlpatterns = [
    path('user/register', RegisterAccount.as_view(), name='user-register'),
    path('user/register/confirm', ConfirmAccount.as_view(), name='user-register-confirm'),
    path('user/login', LoginAccount.as_view(), name='user-login'),
    path('user/details', AccountDetails.as_view(), name='user-details'),
    path('user/details/company', UserCompanies.as_view(), name='user-company-details'),
    path('user/details/company/<pk>/', UserCompanies.as_view(), name='user-company-details'),
    path('user/details/shipto/', UserShipTo.as_view(), name='user-ship-to'),
    path('user/details/shipto/<pk>/', UserShipTo.as_view(), name='user-ship-to'),
    path('filldb/state/', UploadStateCity.as_view(), name='state'),
    path('filldb/state/<pk>/', UploadStateCity.as_view(), name='state'),
    path('filldb/freight/', SetFreightRates.as_view(), name='freight'),
    path('filldb/freight/<pk>/', SetFreightRates.as_view(), name='freight'),
    path('filldb/stocktypes/', SetStockTypes.as_view(), name='stock_types'),
    path('stock/', Stock.as_view(), name='stock'),
    path('stock/<pk>/', Stock.as_view(), name='stock'),
    path('stock/upload/<pk>/', StockItemsUpload.as_view(), name='stock_items_upload'),
    path('stock/items/<pk>/', GetStockItems.as_view(), name='get_stock_items'),
    # path('stock/items/update/<pk>/')
    path('order/', Orders.as_view(), name='ordering'),
    path('order/<pk>/', Orders.as_view(), name='ordering'),


    ]

