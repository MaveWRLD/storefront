from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.include_root_view = False
router.register('products', views.ProductAdminViewSet, basename='admin-products')
router.register('collections', views.CollectionAdminViewSet, basename='admin-collections')

products_router = routers.NestedDefaultRouter(
    router, 'products', lookup='product')
products_router.register('images', views.ProductImageAdminViewSet,
                         basename='admin-product-images')

urlpatterns = router.urls + products_router.urls
