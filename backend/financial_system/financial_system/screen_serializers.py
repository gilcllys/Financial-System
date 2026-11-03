from rest_framework import serializers


class HomeDashboardQuerySerializer(serializers.Serializer):
    month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    year = serializers.IntegerField(required=False, min_value=1, max_value=9999)
