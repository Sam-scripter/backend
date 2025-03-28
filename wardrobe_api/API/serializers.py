from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Profile, Shop, Category, Product, Sale, SaleItem, Order, OrderItem,
    Refund, ShopActivity, Notification, ApprovalRequest
)
from django.db import transaction
from django.conf import settings
from urllib.parse import urljoin

# ------------------------
# User & Profile
# ------------------------
class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['shop', 'role', 'image', 'contact']
        read_only_fields = ['role']

class UserSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    shop = serializers.PrimaryKeyRelatedField(queryset=Shop.objects.all(), required=False)
    role = serializers.ChoiceField(
        choices=['SuperUser', 'Admin', 'Attendant', 'Customer'],
        default='Customer'
    )

    class Meta:
        model = User
        fields = ['username', 'password', 'email', 'first_name', 'last_name', 'shop', 'role']
        extra_kwargs = {'password': {'write_only': True}}

    def validate_role(self, value):
        if value not in ['SuperUser', 'Admin', 'Attendant', 'Customer']:
            raise serializers.ValidationError("Invalid role.")
        return value

    def create(self, validated_data):
        shop = validated_data.pop('shop', None)
        role = validated_data.pop('role', 'Customer').strip()
        user = User.objects.create_user(**validated_data)
        Profile.objects.filter(user=user).update(shop=shop, role=role)
        return user

class UserDetailSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'profile']

    def get_profile(self, obj):
        profile = obj.profile
        return {
            'role': profile.role,
            'contact': profile.contact,
            'image': profile.image.url if profile.image else None,  # The image URL
        }

class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField(required = True)
    password = serializers.CharField(required = True)

class UserChangePasswordSerializer(serializers.Serializer):
   old_password = serializers.CharField()
   new_password = serializers.CharField()

class UserUpdateSerializer(serializers.Serializer):
    username = serializers.CharField(required = False)
    email = serializers.CharField(required = False)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)

class UserDetailSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile']

    def get_profile(self, obj):
        profile = obj.profile
        return {
            'role': profile.role,
            'contact': profile.contact,
            'image': profile.image.url if profile.image else None,
        }


# ------------------------
# Shop
# ------------------------
class ShopSerializer(serializers.ModelSerializer):
    admin = UserDetailSerializer(read_only=True)
    attendants = UserSerializer(many=True)  # Serialize each attendant as a User instance
    sales = serializers.SerializerMethodField()
    revenue = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = ['id', 'name', 'location', 'admin', 'attendants', 'description', 'sales', 'revenue']
        read_only_fields = ['id', 'admin', 'sales', 'revenue']

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.profile.role in ['SuperUser', 'Admin']:
            raise serializers.ValidationError("Only admins can create shops.")
        return attrs

    def get_sales(self, obj):
        return obj.get_total_sales()

    def get_revenue(self, obj):
        return obj.get_total_revenue()

    def update(self, instance, validated_data):
        # Get the list of attendants (User instances)
        attendants_data = validated_data.get('attendants', [])
        attendants = User.objects.filter(id__in=[attendant.id for attendant in attendants_data])

        # Update the instance as usual
        instance = super().update(instance, validated_data)

        # Set the attendants (many-to-many field)
        instance.attendants.set(attendants)  # This will handle the attendants by their User objects
        return instance


# ------------------------
# Category & Product
# ------------------------
class CategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'shop', 'parent', 'description', 'created_at', 'subcategories']
        read_only_fields = ['id', 'created_at']

    def get_subcategories(self, obj):
        return CategorySerializer(obj.subcategories.all(), many=True).data

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'quantity', 'size', 'color', 'image', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be positive.")
        return value

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity cannot be negative.")
        return value
    
    def get_image_url(self, obj):
        # Assuming the request is available in the context
        request = self.context.get('request')
        if obj.image:
            # Generate the full absolute URL for the image
            return request.build_absolute_uri(obj.image.url)
        return None

class CategoryWithProductsSerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True, read_only=True)
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'parent', 'description', 'products', 'subcategories']

    def get_subcategories(self, obj):
        sub_cats = obj.subcategories.all()
        return CategoryWithProductsSerializer(sub_cats, many=True).data

class ShopDetailSerializer(serializers.ModelSerializer):
    admin = UserDetailSerializer(read_only=True)
    attendants = UserDetailSerializer(many=True, read_only=True)
    categories = CategoryWithProductsSerializer(many=True, read_only=True, source='categories')

    class Meta:
        model = Shop
        fields = ['id', 'name', 'location', 'description', 'admin', 'attendants', 'categories']

# ------------------------
# Orders
# ------------------------
class OrderItemSerializer(serializers.Serializer):
    class Meta:
        model = OrderItem
        fields = ['item', 'quantity']

    def validate(self, data):
        if data['quantity'] <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        return data

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)  # Replace DictField with structured serializer
    items_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'shop', 'customer_name', 'customer_phone', 'customer_location', 'items', 'items_detail', 'status', 'order_date']

    def validate_customer_phone(self, value):
        if not value.isdigit() or len(value) < 10:
            raise serializers.ValidationError("Invalid phone number.")
        return value

    def get_items_detail(self, obj):
        return [
            {
                'name': item.item.name,
                'price': item.item.price,
                'quantity': item.quantity,
            } for item in obj.orderitem_set.all()
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        with transaction.atomic():
            order = Order.objects.create(**validated_data)
            total = 0
            for item_data in items_data:
                product = Product.objects.get(id=item_data['id'])
                quantity = item_data['quantity']
                if product.quantity < quantity:
                    raise serializers.ValidationError(f"Insufficient stock for {product.name}")
                OrderItem.objects.create(order=order, item=product, quantity=quantity)
                product.quantity -= quantity
                product.save()
                total += product.price * quantity
            order.total_amount = total
            order.save()
        return order

# ------------------------
# Sales
# ------------------------
class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = ['product', 'quantity', 'price']

class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, source='sale_items')

    class Meta:
        model = Sale
        fields = ['id', 'shop', 'attendant', 'total_amount', 'sale_date', 'items', 'mode_of_payment', 'is_complete']

    def create(self, validated_data):
        # Check if 'items' is present in validated_data
        items_data = validated_data.get('items')
        if not items_data:
            raise serializers.ValidationError("This sale must include at least one item.")
        
        with transaction.atomic():
            # Create the Sale object
            sale = Sale.objects.create(**validated_data)
            total = 0
            
            # Loop over each item and create SaleItem objects
            for item_data in items_data:
                product = item_data['product']  # Get the product from the item data
                quantity = item_data['quantity']  # Get the quantity
                # Check if enough stock is available
                if product.quantity < quantity:
                    raise serializers.ValidationError(f"Insufficient stock for {product.name}")
                # Create SaleItem object
                sale_item = SaleItem.objects.create(
                    sale=sale,  # Associate the Sale with this SaleItem
                    product=product,  # Associate the Product with the SaleItem
                    quantity=quantity,  # Set the quantity
                    price=product.price  # Set the price for this SaleItem
                )
                # Deduct the stock from the product
                product.quantity -= quantity
                product.save()
                # Calculate the total amount of the sale
                total += product.price * quantity

            # Set the total amount for the sale
            sale.total_amount = total
            sale.save()  # Save the sale object with the updated total amount

        return sale


# ------------------------
# Refunds
# ------------------------
class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = '__all__'
        read_only_fields = ['id', 'refunded_at']

# ------------------------
# Shop Activity
# ------------------------
class ShopActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopActivity
        fields = ['id', 'activity_type', 'description', 'timestamp']

# ------------------------
# Notifications
# ------------------------
class NotificationSerializer(serializers.ModelSerializer):
    recipient = UserDetailSerializer(read_only=True)
    sender = UserDetailSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'recipient', 'sender', 'title', 'message', 'is_read', 'created_at']

# ------------------------
# Approval Requests
# ------------------------
class ApprovalRequestSerializer(serializers.ModelSerializer):
    user = UserDetailSerializer(read_only=True)
    shop = ShopSerializer(read_only=True)
    request_type = serializers.ChoiceField(choices=['ShopApproval', 'RefundRequest'])

    class Meta:
        model = ApprovalRequest
        fields = ['id', 'user', 'shop', 'request_type', 'status', 'reason', 'created_at']
