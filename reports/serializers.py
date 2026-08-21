from rest_framework import serializers


class TopProductSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    title = serializers.CharField()
    quantity_sold = serializers.IntegerField()


class SalesReportSerializer(serializers.Serializer):
    order_count = serializers.IntegerField()
    total_sales = serializers.DecimalField(max_digits=19, decimal_places=4)
    top_products = TopProductSerializer(many=True)
