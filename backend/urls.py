from django.urls import path
from django_rest_passwordreset.views import reset_password_request_token, reset_password_confirm

from backend.views import UploadStateCity, RegisterAccount, LoginAccount, AccountDetails, ConfirmAccount, SetFreightRates, SetStockTypes
app_name = 'diplom'

urlpatterns = [
    path('user/register', RegisterAccount.as_view(), name='user-register'),
    path('user/register/confirm', ConfirmAccount.as_view(), name='user-register-confirm'),
    path('user/login', LoginAccount.as_view(), name='user-login'),
    path('filldb/state/', UploadStateCity.as_view(), name='state'),
    path('filldb/state/<pk>/', UploadStateCity.as_view(), name='state'),
    path('filldb/freight/', SetFreightRates.as_view(), name='freight'),
    path('filldb/stocktypes/', SetStockTypes.as_view(), name='stock_types'),


]