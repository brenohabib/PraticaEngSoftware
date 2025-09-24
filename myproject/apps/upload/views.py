from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages

def upload_pdf(request):
    if request.method == 'POST' and request.FILES.get('pdf_file'):
<<<<<<< HEAD
        pdf_file = request.FILES['pdf_file']
=======
        pdf_file = request.FILES['pdf_file']                
>>>>>>> upload_screen
        messages.success(request, f'Arquivo "{pdf_file.name}" enviado com sucesso!')
        return HttpResponseRedirect(reverse('upload_pdf'))
    return render(request, 'upload/upload.html')
