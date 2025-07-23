# BDAuctions_lot_cropper
This repository contains a python program which automatically crops images and adds descriptions for the BD Auctions HiBid sales.


cropper_SAM.py was the first attempt at making the auto-cropper using the open source Segment Anything AI model from Meta. This model had trouble identifying all of the contours of complex auction lots and was not easy to optimize for this use case, so I looked into other AI models to use.

cropper_YOLO.py uses the YOLO v8 Model to identify objects and crop around all the objects identified in the image. It also had some issues correctly identifying the odd objects typically in the images, but lowering the confidence significantly and posting imgsz corrected for this. This correction over identified objects in the image, but this was useful in this case because we are not looking for accuracy in the labels. We want to find all the points where objects are and crop around them so by tweaking these parameters, and then filtering out the useless/errorant small objects it was possible to achieve acceptable levels of accuracy for an image cropping usecase. 

The input and output of the test images are available to see the results from cropper_YOLO.py. 

I used yolov8x.pt on torch & torchvision version 2.3.1+cu121 & 0.18.1+cu121, respectively. I used ultralytics version 8.3.120.
