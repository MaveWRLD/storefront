from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.include_root_view = False
router.register('products', views.ProductAdminViewSet, basename='admin-products')
router.register('collections', views.CollectionAdminViewSet, basename='admin-collections')
router.register('vocabularies', views.VocabularyAdminViewSet,
                basename='admin-vocabularies')

products_router = routers.NestedDefaultRouter(
    router, 'products', lookup='product')
products_router.register('images', views.ProductImageAdminViewSet,
                         basename='admin-product-images')
products_router.register('variants', views.VariantAdminViewSet,
                         basename='admin-product-variants')

# lookup='vocabulary' under a parent whose lookup_field is 'key' gives the
# nested kwarg 'vocabulary_key' (same derivation that turns lookup='product'
# into 'product_pk' above).
vocabularies_router = routers.NestedDefaultRouter(
    router, 'vocabularies', lookup='vocabulary')
vocabularies_router.register('values', views.VocabularyValueAdminViewSet,
                             basename='admin-vocabulary-values')

urlpatterns = router.urls + products_router.urls + vocabularies_router.urls
