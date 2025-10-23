from rest_framework import serializers


class RegisterCustomSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=True,
        allow_null=False
    )
    username = serializers.CharField(
        required=True,
        allow_null=False,
        max_length=124,
    )
    password = serializers.CharField(
        required=True,
        allow_null=False,
    )


class LoginCustomSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=True,
        allow_null=False,
        max_length=124,
    )
    password = serializers.CharField(
        required=True,
        allow_null=False,
    )


class LogoutCustomSerializer(serializers.Serializer):

    user_id = serializers.IntegerField(
        required=True,
        allow_null=False,
    )
    refresh = serializers.CharField(
        required=True,
        allow_null=False,
    )
