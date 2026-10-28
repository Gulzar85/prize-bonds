from allauth.account.adapter import DefaultAccountAdapter

from apps.households.services import create_personal_household


class AccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=commit)
        return user

    def email_verified(self, request, email_address):
        user = email_address.user
        # Create personal household on email verification
        create_personal_household(user)
        return super().email_verified(request, email_address)
