from pathlib import Path

import numpy as np
import tensorflow as tf
from PIL import Image


def load_image(path, max_dim=256):
    image = tf.io.read_file(str(path))
    image = tf.image.decode_image(
        image,
        channels=3,
        expand_animations=False
    )

    image = tf.image.convert_image_dtype(image, tf.float32)

    shape = tf.cast(tf.shape(image)[:2], tf.float32)
    scale = max_dim / tf.reduce_max(shape)
    new_shape = tf.maximum(tf.cast(shape * scale, tf.int32), 1)

    image = tf.image.resize(image, new_shape)

    return image[tf.newaxis, :]


def tensor_to_image(tensor):
    tensor = tf.clip_by_value(tensor, 0.0, 1.0)
    array = np.array(tensor[0] * 255, dtype=np.uint8)

    return Image.fromarray(array)

CONTENT_LAYERS = ["block5_conv2"]

STYLE_LAYERS = [
    "block1_conv1",
    "block2_conv1",
    "block3_conv1",
    "block4_conv1",
    "block5_conv1",
]


def build_extractor():
    vgg = tf.keras.applications.VGG19(
        include_top=False,
        weights="imagenet"
    )

    vgg.trainable = False

    layer_names = STYLE_LAYERS + CONTENT_LAYERS
    outputs = [vgg.get_layer(name).output for name in layer_names]

    return tf.keras.Model(inputs=vgg.input, outputs=outputs)


def gram_matrix(features):
    result = tf.linalg.einsum("bijc,bijd->bcd", features, features)

    shape = tf.shape(features)
    locations = tf.cast(shape[1] * shape[2], tf.float32)

    return result / locations


def extract_features(extractor, image):
    image = tf.keras.applications.vgg19.preprocess_input(image * 255.0)
    outputs = extractor(image)

    style_outputs = outputs[:len(STYLE_LAYERS)]
    content_outputs = outputs[len(STYLE_LAYERS):]

    style_features = [gram_matrix(output) for output in style_outputs]

    return style_features, content_outputs

def generate_image(
    extractor,
    content_image,
    style_image,
    iterations=50,
    style_weight=1e-2,
    content_weight=1e4,
    total_variation_weight=30,
):
    style_targets, _ = extract_features(extractor, style_image)
    _, content_targets = extract_features(extractor, content_image)

    generated_image = tf.Variable(content_image)

    optimizer = tf.keras.optimizers.Adam(learning_rate=0.02)

    for step in range(iterations):
        with tf.GradientTape() as tape:
            style_features, content_features = extract_features(
                extractor,
                generated_image
            )

            style_loss = tf.add_n([
                tf.reduce_mean(tf.square(current - target))
                for current, target in zip(style_features, style_targets)
            ])

            style_loss *= style_weight / len(STYLE_LAYERS)

            content_loss = tf.add_n([
                tf.reduce_mean(tf.square(current - target))
                for current, target in zip(content_features, content_targets)
            ])

            content_loss *= content_weight / len(CONTENT_LAYERS)

            variation_loss = total_variation_weight * tf.reduce_sum(
                tf.image.total_variation(generated_image)
            )

            total_loss = style_loss + content_loss + variation_loss

        gradients = tape.gradient(total_loss, generated_image)

        optimizer.apply_gradients([(gradients, generated_image)])

        generated_image.assign(
            tf.clip_by_value(generated_image, 0.0, 1.0)
        )

        if (step + 1) % 10 == 0:
            print(
                f"Step {step + 1}/{iterations} "
                f"- loss: {float(total_loss):.2f}",
                flush=True
            )

    return generated_image

if __name__ == "__main__":
    upload_folder = Path(__file__).resolve().parent / "uploads"

    run_folders = [
        folder
        for folder in upload_folder.iterdir()
        if (
            folder.is_dir()
            and (folder / "content.png").exists()
            and (folder / "style.png").exists()
        )
    ]

    if not run_folders:
        raise SystemExit("Upload both images through the webpage first.")

    latest_folder = max(
        run_folders,
        key=lambda folder: folder.stat().st_mtime
    )

    content = load_image(latest_folder / "content.png")
    style = load_image(latest_folder / "style.png")

    print("Using folder:", latest_folder.name)
    print("Content shape:", content.shape)
    print("Style shape:", style.shape)
    print("Both images loaded successfully.")
    print("Loading VGG19...")
    extractor = build_extractor()

    style_features, _ = extract_features(extractor, style)
    _, content_features = extract_features(extractor, content)

    print("Style feature groups:", len(style_features))
    print("Content feature groups:", len(content_features))
    print("VGG19 feature extraction successful.")
    print("Starting style transfer...")

    generated = generate_image(
        extractor,
        content,
        style,
        iterations=50
    )

    output_path = latest_folder / "generated.png"

    tensor_to_image(generated).save(output_path)

    print("Generated image saved to:", output_path)