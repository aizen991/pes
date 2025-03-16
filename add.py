import os
import time
import firebase_admin
from firebase_admin import credentials, db, storage, messaging
from pyembroidery import read, write_png
from PIL import Image, ImageDraw, ImageFont
import traceback

# Initialize Firebase
cred = credentials.Certificate('admin.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://ciftec-embroidery-default-rtdb.firebaseio.com/',
    'storageBucket': 'ciftec-embroidery.appspot.com'
})

def upload_to_storage(local_path, storage_path):
    bucket = storage.bucket()
    blob = bucket.blob(storage_path)
    blob.upload_from_filename(local_path)
    if not blob.exists():
        raise Exception(f"Failed to upload {storage_path}")
    return blob.public_url

def upload_to_realtime_db(pes_file_url, image_url, metadata):
    ref = db.reference('embroidery_designs')
    new_entry = ref.push()
    new_entry.set({
        'pes_file_url': pes_file_url,
        'image_url': image_url,
        'metadata': metadata,
        'createdDate': int(time.time() * 1000),
        'id': new_entry.key
    })
    return new_entry.key

def send_embroidery_broadcast(image_url):
    if not image_url:
        print("Error: Image URL is empty.")
        return
    base_url = "https://storage.googleapis.com/ciftec-embroidery.appspot.com/"
    image_path = image_url.replace(base_url, "")
    message = messaging.Message(
        data={"image_url": image_path},
        topic="embroidery_updates",
    )
    try:
        response = messaging.send(message)
        print("Notification sent:", response)
    except Exception as e:
        print("Error sending message:", e)

def add_color_list_and_metadata(image_path, pattern, output_image_path):
    image = Image.open(image_path).convert("RGBA")
    white_bg = Image.new("RGB", image.size, "white")
    white_bg.paste(image, mask=image.split()[3])
    image = white_bg

    threads = getattr(pattern, "threadlist", [])
    width, height = image.size
    new_image = Image.new("RGB", (width + 400, height), "white")
    new_image.paste(image, (0, 0))

    draw = ImageDraw.Draw(new_image)
    font = ImageFont.truetype("arial.ttf", 16)
    header_font = ImageFont.truetype("arial.ttf", 20)
    x_offset, y_offset = width + 20, 10

    draw.text((x_offset, y_offset), "Color List:", fill="black", font=header_font)
    y_offset += 30

    for i, thread in enumerate(threads):
        try:
            red, green, blue = thread.color.red, thread.color.green, thread.color.blue
        except AttributeError:
            red, green, blue = 0, 0, 0
        draw.rectangle([x_offset, y_offset, x_offset + 30, y_offset + 30], fill=(red, green, blue))
        draw.text((x_offset + 40, y_offset + 5), f"Color {i + 1}: ({red}, {green}, {blue})", fill="black", font=font)
        y_offset += 40

    y_offset += 20
    draw.text((x_offset, y_offset), "Metadata:", fill="black", font=header_font)
    y_offset += 30
    extents = pattern.extents()
    metadata = {
        "Author": "StitchMorpher",
        "Width": f"{(extents[2] - extents[0]) / 10:.1f} mm",
        "Height": f"{(extents[3] - extents[1]) / 10:.1f} mm",
        "Stitches": len(pattern.stitches),
        "Color Changes": len(threads),
    }
    for key, value in metadata.items():
        draw.text((x_offset, y_offset), f"{key}: {value}", fill="black", font=font)
        y_offset += 25

    new_image.save(output_image_path)
    return metadata

# Directory containing the PES files
pes_directory = "."

# Process PES files
for pes_file_name in os.listdir(pes_directory):
    if pes_file_name.endswith(".pes"):
        pes_file_path = os.path.join(pes_directory, pes_file_name)
        try:
            temp_png_path = "temp_output.png"
            final_output_path = pes_file_name.replace('.pes', '_output.png')

            pattern = read(pes_file_path)
            write_png(pattern, temp_png_path)
            metadata = add_color_list_and_metadata(temp_png_path, pattern, final_output_path)

            pes_url = upload_to_storage(pes_file_path, f"embroidery_files/{pes_file_name}")
            image_url = upload_to_storage(final_output_path, f"embroidery_images/{final_output_path}")
            db_id = upload_to_realtime_db(pes_url, image_url, metadata)

            send_embroidery_broadcast(image_url)
            print(f"Uploaded {pes_file_name} with Database ID: {db_id}")

            # Remove temporary files
            os.remove(temp_png_path)
            os.remove(final_output_path)
            os.remove(pes_file_path)

            print(f"Deleted temporary files and PES file for {pes_file_name}")

            # Sleep for 5 hours before processing the next file
            print("Sleeping for 5 hours before processing the next file...")
            time.sleep(36000)  # 18000 seconds = 5 hours
        
        except Exception as e:
            print(f"Error processing {pes_file_name}: {e}")
            traceback.print_exc()
