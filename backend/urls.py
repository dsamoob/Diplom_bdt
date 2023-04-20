from django.template.defaulttags import url
from django.urls import path, include
import debug_toolbar

from django.conf import settings
from django_rest_passwordreset.views import reset_password_request_token, reset_password_confirm

from backend.views import UploadStateCity, RegisterAccount, LoginAccount, AccountDetails,\
    ConfirmAccount, SetFreightRates, SetStockTypes, UserCompanies, UserShipTo, StockUploading, StockCorrectionStaff
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
    path('uploadstock/', StockUploading.as_view(), name='stock_uploading'),
    path('uploadstock/<pk>/', StockUploading.as_view(), name='stock_uploading'),
    path('stockcorrection/', StockCorrectionStaff.as_view(), name='stock_correction'),
    path('stockcorrection/<pk>/', StockCorrectionStaff.as_view(), name='stock_correction')

    ]

