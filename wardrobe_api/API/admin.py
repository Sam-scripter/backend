from django.contrib import admin
from .models import Shop, Profile, Order, OrderItem, Sale, SaleItem, Refund, ShopActivity, Category, Product

# Register your models here.
admin.site.register(Shop)
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Profile)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Sale)
admin.site.register(SaleItem)
admin.site.register(Refund)
admin.site.register(ShopActivity)