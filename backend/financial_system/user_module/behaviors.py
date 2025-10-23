from django.contrib.auth.models import User
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken


class RegisterBehavior():
    def __init__(self, data):
        self.data = data

    def registerUser(self):
        return User.objects.create_user(
            username=self.data.get('username'),
            email=self.data.get('email'),
            password=self.data.get('password')
        )

    def run(self):
        if (self.registerUser()):
            return Response(
                'User created',
                status=status.HTTP_201_CREATED
            )
        else:
            return Response(
                'User failed creation',
                status=status.HTTP_400_BAD_REQUEST
            )


class LoginBehavior():
    def __init__(self, data):
        self.data = data

    def verifyUser(self):
        return User.objects.get(
            username=self.data.get('username'),
        )

    def run(self):
        user = self.verifyUser()
        if (self.verifyUser() and user.check_password(raw_password=self.data.get('password'))):
            refresh = RefreshToken.for_user(user)
            return Response(
                {
                    'status': 'Logged',
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {
                    'status': 'Failed',
                },
                status=status.HTTP_400_BAD_REQUEST
            )


class LogoutBehavior():
    def __init__(self, data):
        self.data = data

    def getUser(self):
        return User.objects.get(pk=self.data.get('user_id'))

    def setTokenBlacklist(self):
        token = RefreshToken(self.data.get('refresh'))
        token.blacklist()

    def run(self):
        if (self.getUser()):
            self.setTokenBlacklist()
            return Response(
                {
                    'status': 'Logout and token applied to the blacklist',
                },
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {
                    'status': 'Failed',
                },
                status=status.HTTP_400_BAD_REQUEST
            )
