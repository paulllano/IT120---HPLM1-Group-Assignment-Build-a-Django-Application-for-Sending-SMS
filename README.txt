Step-by-Step How to Run & Demonstrate the Website
Start the Server:

cd "D:\IT120 - Django\sms_project"
.venv\Scripts\Activate.ps1

python manage.py runserver



Open the App: Visit http://127.0.0.1:8000/ in your browser.


Demonstrate Validation (Error Handling):
Click Send SMS with blank fields → shows required field errors.
Enter 12345 as the phone number → shows Philippine mobile format error.



Demonstrate Live SMS Sending:
Ensure the group's Android phone has the SMS Gateway for Android app open with Cloud server enabled and internet connected.
Enter an authorized test number (09XXXXXXXXX) and a message, then click Send SMS.



Demonstrate History & Delivery Confirmation:
Click History in the top navigation bar (/history/).
Select the recipient's conversation thread and click Check status on the message to show it updating to Delivered once received on the handset.
