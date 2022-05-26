
import absl
import os
import sys

from typing import List, Text

import kerastuner
import tensorflow as tf
import tensorflow_transform as tft

from tensorflow.keras import Model
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Input, concatenate

from tfx.components.trainer.fn_args_utils import DataAccessor
from tfx.components.trainer.executor import TrainerFnArgs
from tfx_bsl.tfxio import dataset_options

NUMERIC_FEATURE_KEYS = [
    'age',
    'education-num',
    'capital-gain',
    'capital-loss',
    'hours-per-week',
]
ONE_HOT_FEATURES = {'workclass': 8,
                    'education': 16,
                    'marital-status': 7,
                    'occupation': 14,
                    'relationship': 6,
                    'gender': 2
                   }
LABEL_KEY = 'income'

def transformed_name(key):
    return key + '_xf'

def create_model():
    model = Sequential()

    inputs = []
    for key in NUMERIC_FEATURE_KEYS:
        inputs.append(Input(shape=(1), name=transformed_name(key)))
    for key, dim in ONE_HOT_FEATURES.items():
        for i in range(0, dim):
            inputs.append(Input(shape=(1), name=transformed_name(key + '_' + str(i))))

    outputs = concatenate(inputs)
    units = 100
    outputs = Dense(units, activation='relu')(outputs)
    outputs = Dense(units, activation='relu')(outputs)
    outputs = Dense(1, activation='sigmoid')(outputs)

    model = Model(inputs=inputs, outputs=outputs)
    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
    model.summary()
    return model

def run_fn(fn_args: TrainerFnArgs):
    tf_transform_output = tft.TFTransformOutput(fn_args.transform_output)
    train_dataset = input_fn(fn_args.train_files, fn_args.data_accessor,
                                tf_transform_output, 40)
    eval_dataset = input_fn(fn_args.eval_files, fn_args.data_accessor,
                               tf_transform_output, 40)

    tensorboard_callback = tf.keras.callbacks.TensorBoard(
        log_dir = fn_args.model_run_dir, update_freq='batch'
    )

    model = create_model()
    model.fit(
        train_dataset,
        epochs = fn_args.custom_config["epoch"],
        steps_per_epoch = fn_args.train_steps,
        validation_data = eval_dataset,
        validation_steps = fn_args.eval_steps,
        callbacks = [tensorboard_callback]
    )

    signatures = {
        'serving_default':
            get_tf_examples_serving_signature(model, tf_transform_output),
        'transform_features':
            get_transform_features_signature(model, tf_transform_output),
    }
    model.save(fn_args.serving_model_dir, save_format='tf', signatures=signatures)

def input_fn(file_pattern: List[Text],
             data_accessor: DataAccessor,
             tf_transform_output: tft.TFTransformOutput,
             batch_size: int = 200) -> tf.data.Dataset:
    return data_accessor.tf_dataset_factory(
        file_pattern,
        dataset_options.TensorFlowDatasetOptions(
            batch_size=batch_size, label_key=transformed_name(LABEL_KEY)),
        tf_transform_output.transformed_metadata.schema)

def get_tf_examples_serving_signature(model, tf_transform_output):
    model.tft_layer_inference = tf_transform_output.transform_features_layer()

    @tf.function(input_signature=[
        tf.TensorSpec(shape=[None], dtype=tf.string, name='examples')
    ])
    def serve_tf_examples_fn(serialized_tf_example):
        raw_feature_spec = tf_transform_output.raw_feature_spec()
        raw_feature_spec.pop(LABEL_KEY)
        raw_features = tf.io.parse_example(serialized_tf_example, raw_feature_spec)
        transformed_features = model.tft_layer_inference(raw_features)

        outputs = model(transformed_features)
        return {'outputs': outputs}

    return serve_tf_examples_fn

def get_transform_features_signature(model, tf_transform_output):
    model.tft_layer_eval = tf_transform_output.transform_features_layer()

    @tf.function(input_signature=[
        tf.TensorSpec(shape=[None], dtype=tf.string, name='examples')
    ])
    def transform_features_fn(serialized_tf_example):
        raw_feature_spec = tf_transform_output.raw_feature_spec()
        raw_features = tf.io.parse_example(serialized_tf_example, raw_feature_spec)
        transformed_features = model.tft_layer_eval(raw_features)
        return transformed_features

    return transform_features_fn
