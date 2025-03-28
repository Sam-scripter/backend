from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework import viewsets, permissions, generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import (
    Shop, Category, Product, Sale,
    Order, Refund, Notification, ApprovalRequest,
    ShopActivity
)
from .serializers import (
    UserSerializer, UserDetailSerializer, 
    ShopSerializer, ShopDetailSerializer, CategoryWithProductsSerializer,
    ProductSerializer, SaleSerializer,
    OrderSerializer, RefundSerializer, NotificationSerializer,
    ApprovalRequestSerializer, ShopActivitySerializer, UserLoginSerializer, UserChangePasswordSerializer, UserUpdateSerializer, CategorySerializer
)
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404


# -------------------------- AUTH --------------------------

class UserRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'message': 'User registered successfully'
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = authenticate(
                request,
                username=serializer.validated_data.get('username'),
                password=serializer.validated_data.get('password')
            )
            if not user:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

            tokens = self.get_serializer(data=request.data)
            tokens.is_valid(raise_exception=True)

            profile = user.profile
            response_data = {
                'id': user.id,
                'access': tokens.validated_data.get('access'),
                'refresh': tokens.validated_data.get('refresh'),
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': profile.role,
                'image': request.build_absolute_uri(profile.image.url) if profile.image else None
            }

            if profile.first_login:
                response_data['first_login'] = True
                response_data['message'] = 'Please change your password'
                return Response(response_data, status=status.HTTP_206_PARTIAL_CONTENT)

            if profile.role in ['Admin', 'Attendant'] and profile.shop:
                response_data['shop'] = {'id': profile.shop.id, 'name': profile.shop.name}

            return Response(response_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            RefreshToken(refresh_token).blacklist()
            return Response({'message': 'Logged out successfully'}, status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response({'error': 'Invalid refresh token'}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = UserChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({'error': 'Incorrect old password'}, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(serializer.validated_data['new_password'])
            user.profile.first_login = False
            user.profile.save()
            user.save()
            return Response({'message': 'Password changed successfully'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserDetailsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserDetailSerializer(request.user).data)

    def put(self, request):
        serializer = UserUpdateSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user

            
            for field in serializer.validated_data:
                setattr(user, field, serializer.validated_data[field])

            
            if 'contact' in serializer.validated_data:
                user.profile.contact = serializer.validated_data['contact']
                print(serializer.validated_data['contact'])

          
            if 'image' in request.FILES:
                user.profile.image = request.FILES['image']
            
           
            user.save()
            user.profile.save()  

            return Response({'message': 'Updated successfully'})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class UserListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserDetailSerializer
    permission_classes = [permissions.IsAuthenticated]


# -------------------------- SHOP --------------------------

class ShopViewSet(viewsets.ModelViewSet):
    serializer_class = ShopSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.profile.role == 'SuperUser':
            return Shop.objects.all()
        return Shop.objects.filter(admin=user)

    def perform_create(self, serializer):
        serializer.save(admin=self.request.user)
        # Create the shop
        shop = serializer.save(admin=self.request.user)

        # Send a notification when a shop is created
        send_notification(
            self.request.user,
            "New Shop Created",
            f"A new shop '{shop.name}' has been created."
        )

    def perform_update(self, serializer):
        # Update the shop
        shop = serializer.save()

        # Send a notification when a shop is updated
        send_notification(
            self.request.user,
            "Shop Updated",
            f"The shop '{shop.name}' has been updated."
        )

    def destroy(self, request, *args, **kwargs):
        shop = self.get_object()
        if shop.admin != request.user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def recent_activities(self, request, pk=None):
        shop = self.get_object()
        activities = shop.activities.order_by("-timestamp")[:10]
        return Response(ShopActivitySerializer(activities, many=True).data)


class ShopDetailAPIView(generics.RetrieveAPIView):
    queryset = Shop.objects.all()
    serializer_class = ShopDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

# -------------------------- CATEGORY --------------------------

class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Category.objects.filter(shop__admin=self.request.user)

    def perform_create(self, serializer):
        shop_id = self.request.data.get("shop")
        shop = Shop.objects.get(id=shop_id, admin=self.request.user)
        category = serializer.save()
        # Send notification for category creation
        send_notification(
            self.request.user,
            "New Category Created",
            f"A new category '{category.name}' has been created."
        )

    def perform_update(self, serializer):
        category = serializer.save()

        # Send notification for category update
        send_notification(
            self.request.user,
            "Category Updated",
            f"The category '{category.name}' has been updated."
        )

    def perform_destroy(self, instance):
        category_name = instance.name
        # Delete the category
        instance.delete()

        # Send notification for category deletion
        send_notification(
            self.request.user,
            "Category Deleted",
            f"The category '{category_name}' has been deleted."
        )

    @action(detail=False, methods=['get'], url_path='shop/(?P<shop_id>[^/.]+)/categories')
    def categories_by_shop(self, request, shop_id=None):
        try:
            # Check if the user is a SuperUser via Profile
            is_superuser = hasattr(request.user, 'profile') and request.user.profile.role == 'SuperUser'

            if is_superuser:
                categories = Category.objects.filter(shop__id=shop_id)
            else:
                categories = Category.objects.filter(shop__id=shop_id, shop__admin=request.user)

            context = {'request': request}
            serializer = CategoryWithProductsSerializer(categories, many=True, context=context)
            return Response(serializer.data)
            
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    
    @action(detail=True, methods=['get'], url_path='subcategories-with-products')
    def subcategories_with_products(self, request, pk=None):
        category = self.get_object()  # Get the specific category by pk (categoryId)
        
        # Fetch products of the category
        products = category.products.all()
        products_serializer = ProductSerializer(products, many=True)
        
        # Fetch subcategories of the category
        subcategories = category.subcategories.all()
        subcategories_serializer = CategorySerializer(subcategories, many=True)
        
        # Prepare the response data
        data = {
            "category": CategorySerializer(category).data,
            "subcategories": subcategories_serializer.data,
            "products": products_serializer.data,
        }

        return Response(data)

    @action(detail=True, methods=['get'], url_path='category-with-products')
    def category_with_products(self, request, pk=None):
        category = self.get_object()
        
        # Fetch products of the category
        products = category.products.all()
        products_serializer = ProductSerializer(products, many=True)
        
        # Prepare the response data
        data = {
            "category": CategorySerializer(category).data,
            "products": products_serializer.data,
        }

        return Response(data)
    
    

# -------------------------- PRODUCT --------------------------

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny] #to change to permissions.Authenticated

    # def get_queryset(self):
    #     return Product.objects.filter(category__shop__admin=self.request.user) ----Uncomment this line

    def get_queryset(self):
        return Product.objects

    def perform_create(self, serializer):
        if serializer.validated_data['category'].shop.admin != self.request.user:
            raise ValidationError("Unauthorized to add product to this shop.")
        product = serializer.save()

        # Send notification for product creation
        send_notification(
            self.request.user,
            "New Product Created",
            f"A new product '{product.name}' has been added."
        )

    def perform_update(self, serializer):
        product = serializer.save()

        # Send notification for product update
        send_notification(
            self.request.user,
            "Product Updated",
            f"The product '{product.name}' has been updated."
        )

    def perform_destroy(self, instance):
        product_name = instance.name
        # Delete the product
        instance.delete()

        # Send notification for product deletion
        send_notification(
            self.request.user,
            "Product Deleted",
            f"The product '{product_name}' has been deleted."
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request  # Make sure to pass the request object
        return context

# -------------------------- SALE --------------------------

class SaleViewSet(viewsets.ModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Sale.objects.filter(shop__admin=self.request.user)

    def perform_create(self, serializer):
        print(f"Received data: {self.request.data}")
        try:
            sale = serializer.save(attendant=self.request.user)
            # Send notification for sale creation
            send_notification(
                self.request.user,
                "New Sale",
                f"A new sale '{sale.id}' has been recorded.",
                type_id=sale.id,
                notification_type= "Sale",                
            )
        except ValidationError as e:
            print("Validation error: ", e)
            raise e 

    def perform_update(self, serializer):
        sale = serializer.save()

        # Send notification for sale update
        send_notification(
            self.request.user,
            "Sale Updated",
            f"The sale '{sale.id}' has been updated."
        )

    def perform_destroy(self, instance):
        sale_id = instance.id
        # Delete the sale
        instance.delete()

        # Send notification for sale deletion
        send_notification(
            self.request.user,
            "Sale Deleted",
            f"The sale '{sale_id}' has been deleted."
        )

# -------------------------- ORDER --------------------------

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(shop__admin=self.request.user)
    
    def perform_create(self, serializer):
        order = serializer.save()

        # Send notification for order creation
        send_notification(
            self.request.user,
            "New Order",
            f"A new order '{order.id}' has been placed."
        )

    def perform_update(self, serializer):
        order = serializer.save()

        # Send notification for order update
        send_notification(
            self.request.user,
            "Order Updated",
            f"The order '{order.id}' has been updated."
        )

    def perform_destroy(self, instance):
        order_id = instance.id
        # Delete the order
        instance.delete()

        # Send notification for order deletion
        send_notification(
            self.request.user,
            "Order Deleted",
            f"The order '{order_id}' has been deleted."
        )

# -------------------------- REFUND --------------------------

class RefundViewSet(viewsets.ModelViewSet):
    serializer_class = RefundSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Refund.objects.filter(shop__admin=self.request.user)
    
    def perform_create(self, serializer):
        refund = serializer.save()

        # Send notification for refund creation
        send_notification(
            self.request.user,
            "New Refund Request",
            f"A new refund request has been made for order '{refund.order.id}'."
        )

    def perform_update(self, serializer):
        refund = serializer.save()

        # Send notification for refund update
        send_notification(
            self.request.user,
            "Refund Updated",
            f"The refund request for order '{refund.order.id}' has been updated."
        )

    def perform_destroy(self, instance):
        refund_order_id = instance.order.id
        # Delete the refund
        instance.delete()

        # Send notification for refund deletion
        send_notification(
            self.request.user,
            "Refund Deleted",
            f"The refund request for order '{refund_order_id}' has been deleted."
        )

# -------------------------- NOTIFICATION --------------------------

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)


# -------------------------- SHOP ACTIVITY --------------------------
class ShopActivityViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for viewing and editing shop activities.
    """
    queryset = ShopActivity.objects.all().order_by('-timestamp')
    serializer_class = ShopActivitySerializer

# -------------------------- ADMIN APPROVAL REQUEST --------------------------
class ApprovalRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing approval requests with custom approval/rejection actions.
    """
    queryset = ApprovalRequest.objects.all().order_by('-submitted_at')
    serializer_class = ApprovalRequestSerializer

    def get_queryset(self):
        """
        Optionally filters by status if 'status' query parameter is provided.
        """
        queryset = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Custom action to approve a request."""
        approval_request = self.get_object()
        approval_request.status = 'approved'
        approval_request.save()
        
        # Send notification for request approval
        send_notification(
            approval_request.admin,
            "Request Approved",
            f"The request for shop {approval_request.shop.name} has been approved."
        )
        
        return Response({'status': 'request approved'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Custom action to reject a request."""
        approval_request = self.get_object()
        approval_request.status = 'rejected'
        approval_request.save()
        
        # Send notification for request rejection
        send_notification(
            approval_request.admin,
            "Request Rejected",
            f"The request for shop {approval_request.shop.name} has been rejected."
        )
        
        return Response({'status': 'request rejected'}, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        """Automatically sets the requesting user when creating a new request."""
        serializer.save(user=self.request.user)




def send_notification(
    user: User, 
    title: str, 
    message: str, 
    notification_type: str,
    type_id: int,
    
):
    """
    Generic function to create a notification.
    """
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        type_id=type_id,
        read=False,
        timestamp=timezone.now()
    )
    # Optionally, you can send a push notification here if needed.
    return notification
