from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.include_root_view = False
router.register('products', views.ProductViewSet, basename='products')
router.register('collections', views.CollectionViewSet, basename='collections')

products_router = routers.NestedDefaultRouter(
    router, 'products', lookup='product')
products_router.register('reviews', views.ReviewViewSet,
                         basename='product-reviews')
products_router.register('images', views.ProductImageViewSet,
                         basename='product-images')

urlpatterns = router.urls + products_router.urls
