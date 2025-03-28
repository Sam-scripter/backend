from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserRegistrationView,
    UserLoginView,
    UserLogoutView,
    ChangePasswordView,
    UserDetailsView,
    UserListView,
    ShopViewSet,
    ShopDetailAPIView,
    CategoryViewSet,
    ProductViewSet,
    SaleViewSet,
    OrderViewSet,
    RefundViewSet,
    ShopActivityViewSet,
    NotificationViewSet,
    ApprovalRequestViewSet,
)

# DRF router for ViewSets
router = DefaultRouter()
router.register(r'shops', ShopViewSet, basename='shop')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'sales', SaleViewSet, basename='sale')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'refunds', RefundViewSet, basename='refund')
router.register(r'activities', ShopActivityViewSet, basename='activity')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'approval-requests', ApprovalRequestViewSet, basename='approval-request')

urlpatterns = [
    path('', include(router.urls)),

    # Authentication
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('login/', UserLoginView.as_view(), name='login'),
    path('logout/', UserLogoutView.as_view(), name='logout'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),

    # User
    path('user-details/', UserDetailsView.as_view(), name='user_details'),
    path('users-details/', UserListView.as_view(), name='users_details'),


    # Shop detail (with categories & products)
    path('shops/<int:pk>/', ShopDetailAPIView.as_view(), name='shop-detail'),
]
