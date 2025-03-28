from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError
from django.db import transaction
from decimal import Decimal


# ----------------------------
# Shop
# ----------------------------
class Shop(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, null=True)
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='admin_shops')
    attendants = models.ManyToManyField(User, related_name='attendant_shops', blank=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_total_sales(self):
        total_sales = sum(sale.get_items_quantity() for sale in self.sale_set.all())
        total_sales += sum(order.get_items_quantity() for order in self.order_set.all())
        return total_sales

    from decimal import Decimal

    def get_total_revenue(self):
        total_revenue = sum(Decimal(sale.total_amount) for sale in self.sale_set.all())
        total_revenue += sum(Decimal(order.get_total_price()) for order in self.order_set.all())
        return total_revenue


class Profile(models.Model):
    USER_ROLES = [
        ('SuperUser', 'SuperUser'),
        ('Admin', 'Admin'),
        ('Attendant', 'Attendant'),
        ('Customer', 'Customer'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    shop = models.ForeignKey(Shop, blank=True, null=True, on_delete=models.CASCADE, related_name='shop_profiles')
    role = models.CharField(max_length=20, choices=USER_ROLES, default='Customer')
    image = models.ImageField(upload_to='profiles/', null=True, blank=True)
    contact = models.CharField(max_length=20, blank=True, null=True)
    first_login = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    #payment method(Implementing Mpesa Stk Push) require an admin to set up Paybill or Till

    def save(self, *args, **kwargs):
        if not self.pk and self.role == 'Attendant':
            self.first_login = True
        else:
            self.first_login = False
        if self.role == 'Attendant' and not self.shop:
            raise ValueError("Attendants must be assigned to a shop.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username}'s Profile"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

# ----------------------------
# Inventory: Category & Product
# ----------------------------
class Category(models.Model):
    name = models.CharField(max_length=100)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='categories')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subcategories')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('name', 'shop')

    def __str__(self):
        return self.name

class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    size = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# ----------------------------
# Order & Sale
# ----------------------------
class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Intransit', 'Intransit'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="order_set")
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    customer_location = models.CharField(max_length=255, blank=True, null=True)
    order_date = models.DateTimeField(auto_now_add=True)
    products = models.ManyToManyField(Product, through='OrderItem')
    total_amount = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order for {self.shop.name}"

    def get_items_quantity(self):
        return sum(item.quantity for item in self.orderitem_set.all())

    def get_total_price(self):
        return sum(item.product.price * item.quantity for item in self.orderitem_set.all())

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

class Sale(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="sale_set")
    attendant = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    sale_date = models.DateTimeField(auto_now_add=True)
    products = models.ManyToManyField(Product, through='SaleItem')
    total_amount = models.FloatField(default=0)
    mode_of_payment = models.CharField(max_length=255, default="Cash")
    is_complete = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_refunded = models.BooleanField(default=False)
    refund_date = models.DateTimeField(null=True, blank=True)
    total_refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"Sale for {self.shop.name}"

    def get_items_quantity(self):
        return sum(item.quantity for item in self.sale_items.all())

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name='sale_items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.FloatField()

# ----------------------------
# Refunds
# ----------------------------

class Refund(models.Model):
    REFUND_TYPE_CHOICES = [
        ('Order', 'Order'),
        ('Sale', 'Sale'),
    ]

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="refunds")
    refund_type = models.CharField(max_length=10, choices=REFUND_TYPE_CHOICES)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, null=True, blank=True, related_name="refunds")
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True, related_name="refunds")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField(blank=True, null=True)
    refunded_at = models.DateTimeField(default=now)

    def clean(self):
        # Check if the refund request has been approved by the admin
        approval_request = ApprovalRequest.objects.filter(
            shop=self.shop,
            request_type='Refund',
            status='Approved'
        ).first()

        if not approval_request:
            raise ValidationError("Refund request is not approved by an admin.")

        if self.refund_amount > (self.product.price * self.quantity):
            raise ValidationError("Refund amount cannot exceed item value.")

    def save(self, *args, **kwargs):
        # Perform validation checks
        self.clean()

        # Adjust the sale or order associated with the refund
        with transaction.atomic():
            # Save the refund first
            super().save(*args, **kwargs)

            # Handle refund for Sale
            if self.refund_type == 'Sale' and self.sale:
                sale = self.sale
                # Deduct refund amount from the sale's total amount
                sale.total_amount -= self.refund_amount
                sale.total_refunded_amount += self.refund_amount
                sale.save()

                # Update product stock for the refunded quantity
                product = self.product
                product.quantity += self.quantity  # Restore the refunded quantity to stock
                product.save()

                # If the total refunded amount matches or exceeds the sale's total amount, mark as refunded
                if sale.total_refunded_amount >= sale.total_amount:
                    sale.is_refunded = True
                    sale.save()

            # Handle refund for Order (partial refund, same as before)
            elif self.refund_type == 'Order' and self.order:
                order = self.order
                # Adjust the order total amount by subtracting the refund amount
                order.total_amount -= self.refund_amount
                order.save()

                # Partial refund, check the remaining items in the order to determine the status
                remaining_items = order.get_items_quantity()  # Total quantity of non-refunded items
                refunded_items = sum([refund.quantity for refund in order.refunds.all()])  # Total refunded quantity

                # If all items have been refunded, mark the order as 'Cancelled'
                if refunded_items >= remaining_items:
                    order.status = 'Cancelled'
                    order.save()

                # Update product stock for the refunded quantity
                product = self.product
                product.quantity += self.quantity  # Restore the refunded quantity to stock
                product.save()

    def __str__(self):
        return f"Refund #{self.id} - {self.refund_type} - {self.product.name}"

# ----------------------------
# Notifications
# ----------------------------

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    message = models.TextField(null=True, blank=True)
    notification_type = models.CharField(max_length=100, null=True, blank=True)
    type_id = models.IntegerField(null=True, blank=True)
    read = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"To {self.user.username}: {self.title}"

# ----------------------------
# Approval Requests
# ----------------------------

class ApprovalRequest(models.Model):
    REQUEST_TYPES = [
        ('Seller', 'Seller'),  # Change from Customer to Admin
        ('Refund', 'Refund Approval'),  # Refund request approval
    ]
    
    PHASES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Completed', 'Completed'),
    ]

    request_type = models.CharField(max_length=20, choices=REQUEST_TYPES)
    reason = models.TextField(blank=True, null=True)  # For rejections or reasons for approval
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='approval_requests')  # Admin user creating the request
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='approval_requests')  # Shop for the request
    status = models.CharField(max_length=20, choices=[('Pending', 'Pending'), ('Approved', 'Approved'), ('Rejected', 'Rejected')], default='Pending')
    phase = models.CharField(max_length=20, choices=PHASES, default='Pending')  # Tracks request's phase
    submitted_at = models.DateTimeField(auto_now_add=True)

    # Additional fields to track refund and seller details
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, null=True, blank=True, related_name="approval_requests")
    user_requesting_role_change = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="seller_approval_requests")

    def __str__(self):
        return f"{self.admin.username}'s request for {self.shop.name} ({self.request_type})"

    def approve_refund(self):
        """Approve a refund request. This method should be called by the shop's admin."""
        if self.request_type != 'Refund':
            raise ValidationError("This is not a Refund approval request.")
        
        if self.status != 'Approved':
            raise ValidationError("Refund request is not approved by an admin.")

        # If approval is granted, update the phase and status of the request
        self.status = 'Approved'
        self.save()

    def approve_seller(self):
        """Approve a seller request. This method should be called by the superuser."""
        if self.request_type != 'Seller':
            raise ValidationError("This is not a Seller approval request.")
        
        # Only a superuser can approve the seller request
        if self.admin.role != 'SuperUser':
            raise ValidationError("Only SuperUser can approve Seller requests.")
        
        # Change the user's role to 'Admin' upon approval
        self.admin.profile.role = 'Admin'
        self.admin.profile.save()
        
        # Mark the phase as 'Completed' when the approval is finalized
        self.phase = 'Completed'
        self.save()

    def get_refund_details(self):
        """Helper function to get the details of the refund associated with the approval request."""
        if self.refund:
            return {
                'product': self.refund.product.name,
                'quantity': self.refund.quantity,
                'refund_amount': self.refund.refund_amount,
                'reason': self.refund.reason,
                'order_id': self.refund.order.id if self.refund.order else None,
                'sale_id': self.refund.sale.id if self.refund.sale else None,
            }
        return None

    def get_seller_details(self):
        """Helper function to get the details of the seller requesting role change."""
        if self.user_requesting_role_change:
            return {
                'username': self.user_requesting_role_change.username,
                'email': self.user_requesting_role_change.email,
                'contact': self.user_requesting_role_change.profile.contact,
                'location': self.user_requesting_role_change.profile.shop.address if self.user_requesting_role_change.profile.shop else None,
                'role': self.user_requesting_role_change.profile.role,
            }
        return None
    

# ----------------------------
# Shop Activity
# ----------------------------
class ShopActivity(models.Model):
    ACTIVITY_TYPES = [
        ('SALE', 'Sale'),
        ('ORDER', 'Order'),
        ('REFUND', 'Refund'),
    ]
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    shop = models.ForeignKey("Shop", on_delete=models.CASCADE, related_name="activities")
    description = models.TextField()
    timestamp = models.DateTimeField(default=now)

    def __str__(self):
        return f"{self.shop.name} - {self.activity_type}"