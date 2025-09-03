from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.contrib.auth import logout
from django.views.decorators.csrf import csrf_exempt
import razorpay

from .models import (
    Product, CartItem, Cart, AboutPage, ContactMessage,
    HeroSection, Category, AboutSection, Banner, Offer, SiteTheme,
    FeaturedProduct, BestSeller, NewArrival, Order, OrderItem
)
from .forms import NewsletterForm, ProductReviewForm, CheckoutForm, ContactForm

# ----------------- HOME -----------------
def home(request):
    context = {
        'hero_slides': HeroSection.objects.filter(active=True),
        'categories': Category.objects.all(),
        'about': AboutSection.objects.first(),
        'banners': Banner.objects.filter(active=True),
        'current_offers': Offer.objects.filter(active=True),
        'theme': SiteTheme.objects.first(),
        'featured_products': FeaturedProduct.objects.filter(active=True),
        'best_sellers': BestSeller.objects.filter(active=True),
        'new_arrivals': NewArrival.objects.filter(active=True),
        'offers': Offer.objects.filter(active=True),
    }
    return render(request, 'store/home.html', context)

# ----------------- STATIC PAGES -----------------
def about(request):
    return render(request, "store/about.html", {"about_page": AboutPage.objects.first()})

def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Your message has been sent successfully!")
            return redirect("contact")
        messages.error(request, "There was an error. Please check the form.")
    else:
        form = ContactForm()
    return render(request, "store/contact.html", {"form": form})

def register(request):
    return render(request, 'store/register.html')

# ----------------- SHOP -----------------
def shop(request):
    category_id = request.GET.get('category')
    query = request.GET.get('q')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    sort_by = request.GET.get('sort_by')

    products = Product.objects.all()
    categories = Category.objects.all()
    selected_category = None

    if category_id:
        try:
            selected_category = int(category_id)
            if categories.filter(id=selected_category).exists():
                products = products.filter(category_id=selected_category)
        except ValueError:
            selected_category = None

    if query:
        products = products.filter(title__icontains=query)

    if min_price:
        products = products.filter(price__gte=min_price)
    if max_price:
        products = products.filter(price__lte=max_price)

    if sort_by == "price_asc":
        products = products.order_by('price')
    elif sort_by == "price_desc":
        products = products.order_by('-price')
    elif sort_by == "newest":
        products = products.order_by('-created_at')

    paginator = Paginator(products, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'store/shop.html', {
        'products': page_obj,
        'categories': categories,
        'selected_category': selected_category,
        'page_obj': page_obj,
        'query': query,
        'min_price': min_price,
        'max_price': max_price,
        'sort_by': sort_by,
    })


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return render(request, 'store/product_detail.html', {'product': product})

# ----------------- CART -----------------
@login_required
def cart(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render(request, 'store/cart.html', {'cart_items': cart_items, 'total': total})

@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    if not created:
        cart_item.quantity += 1
    cart_item.subtotal = cart_item.quantity * cart_item.product.price
    cart_item.save()
    messages.success(request, f"{product.title} added to cart.")
    return redirect('shop')

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    product = get_object_or_404(Product, id=product_id)
    cart_item = CartItem.objects.filter(cart=cart, product=product).first()
    if cart_item:
        cart_item.delete()
    return redirect('cart')  # redirect back to cart page

@login_required
def update_cart(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        try:
            quantity = int(request.POST.get('quantity'))
            if quantity > 0:
                item.quantity = quantity
                item.subtotal = item.quantity * item.product.price
                item.save()
            else:
                item.delete()
        except (ValueError, TypeError):
            messages.error(request, "Invalid quantity.")
    return redirect('cart')

# ----------------- CHECKOUT & PAYMENT -----------------
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Cart, CartItem, Order, OrderItem
from .forms import CheckoutForm

@login_required
def checkout(request):
    cart = get_object_or_404(Cart, user=request.user)
    cart_items = CartItem.objects.filter(cart=cart)

    # Prepare order items with subtotal
    order_items = []
    for item in cart_items:
        order_items.append({
            'product': item.product,
            'quantity': item.quantity,
            'price': item.product.price,
            'subtotal': item.product.price * item.quantity
        })

    # Calculate cart total
    cart_total = sum(item['subtotal'] for item in order_items)

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.user = request.user
            order.total_amount = cart_total
            order.save()

            for item in order_items:
                OrderItem.objects.create(
                    order=order,
                    product=item['product'],
                    quantity=item['quantity'],
                    price=item['price']
                )

            cart_items.delete()  # clear cart
            messages.success(request, "Your order has been placed successfully!")
            return redirect('payment_page', order_id=order.id)
    else:
        form = CheckoutForm()

    context = {
        'form': form,
        'order': {
            'items': order_items,
            'total_amount': cart_total
        }
    }

    return render(request, 'store/checkout.html', context)

def payment_page(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    amount = int(order.total_amount * 100)  # Convert to paise

    if amount < 100:
        amount = 100  # Razorpay minimum ₹1 (100 paise)

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    razorpay_order = client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": "1"
    })

    return render(request, "store/payment.html", {
    "order": order,
    "razorpay_key": settings.RAZORPAY_KEY_ID,
    "razorpay_order_id": razorpay_order["id"],
    "razorpay_amount": razorpay_order["amount"],
})

@csrf_exempt
def payment_success(request):
    return render(request, 'store/payment_success.html')

# ----------------- SEARCH -----------------
def shop_search(request):
    query = request.GET.get('q', '')
    products = Product.objects.filter(Q(title__icontains=query) | Q(description__icontains=query))
    categories = Category.objects.all()
    return render(request, 'store/shop.html', {
        'products': products,
        'categories': categories,
        'query': query
    })

# ----------------- SIGNUP & PROFILE -----------------
def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'store/signup.html', {'form': form})

@login_required
def profile_view(request):
    return render(request, 'store/profile.html')

# ----------------- NEWSLETTER -----------------
def newsletter_subscribe(request):
    if request.method == "POST":
        email = request.POST.get("email")
        if email:
            from .models import NewsletterSubscriber
            subscriber, created = NewsletterSubscriber.objects.get_or_create(email=email)
            if created:
                messages.success(request, "Thank you for subscribing!")
            else:
                messages.info(request, "You are already subscribed.")
        else:
            messages.error(request, "Please enter a valid email.")
    return redirect("home")

# ----------------- ORDER HISTORY -----------------
@login_required
def order_history(request):
    orders = Order.objects.filter(user=request.user).order_by('-date_ordered')
    return render(request, 'store/order_history.html', {'orders': orders})

# ----------------- PRODUCT REVIEW -----------------
@login_required
def add_review(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        form = ProductReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.user = request.user
            review.product = product
            review.save()
            messages.success(request, "Your review has been submitted!")
            return redirect('product_detail', pk=product.id)
    else:
        form = ProductReviewForm()
    return render(request, 'store/add_review.html', {'form': form, 'product': product})

# ----------------- AUTH -----------------
def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('home')

# ----------------- CART QUANTITY -----------------
@login_required
def increase_quantity(request, product_id):
    cart_item = get_object_or_404(CartItem, cart__user=request.user, product_id=product_id)

    cart_item.quantity += 1
    cart_item.save()

    return redirect('cart')  # Replace with your cart page URL



@login_required
def decrease_quantity(request, product_id):
    # Fetch the CartItem, not Cart
    cart_item = get_object_or_404(CartItem, cart__user=request.user, product_id=product_id)

    if cart_item.quantity > 1:
        cart_item.quantity -= 1
        cart_item.save()
    else:
        cart_item.delete()

    return redirect('cart')

@login_required
def cart_view(request):
    # Get all items in the user's cart
    cart_items = CartItem.objects.filter(cart__user=request.user)

    # Calculate total
    total = sum(item.product.price * item.quantity for item in cart_items)

    context = {
        'cart_items': cart_items,
        'total': total,
    }
    return render(request, 'store/cart.html', context)


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    products = Product.objects.filter(category=category)
    context = {
        'category': category,
        'products': products
    }
    return render(request, 'store/category_detail.html', context)