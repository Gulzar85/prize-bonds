from django import forms

from apps.draws.models import Denomination


class ReviewDecisionForm(forms.Form):
    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Note (required)",
        help_text="Say what you checked, or why you are rejecting.",
    )
    override_errors = forms.BooleanField(
        required=False,
        label="Publish despite the error findings above",
        help_text="Only after checking the source; the note is recorded with the override.",
    )

    def clean_note(self) -> str:
        note: str = self.cleaned_data["note"].strip()
        if not note:
            raise forms.ValidationError("A written note is required.")
        return note


class UploadRevisionForm(forms.Form):
    denomination = forms.ModelChoiceField(queryset=Denomination.objects.filter(is_active=True))
    draw_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    file = forms.FileField(help_text="TXT, PDF, DOC or DOCX, at most 20 MB.")
