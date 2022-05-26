import os
import sys

import tensorflow as tf
import tensorflow_transform as tft

# 数値変数の項目名リスト
NUMERIC_FEATURE_KEYS = [
    'age',
    'education-num',
    'capital-gain',
    'capital-loss',
    'hours-per-week',
]
# カテゴリー変数の項目名とその次元数の辞書
ONE_HOT_FEATURES = {'workclass': 8,
                    'education': 16,
                    'marital-status': 7,
                    'occupation': 14,
                    'relationship': 6,
                    'gender': 2
                   }
# 予測対象の項目名
LABEL_KEY = 'income'

# 変換後の項目名の変換用関数
def transformed_name(key):
    return key + '_xf'

def preprocessing_fn(inputs):
    #文字列型の値を数値型に変換する関数
    def __convert_string2int_value(key, original_values, converted_values):
        initializer = tf.lookup.KeyValueTensorInitializer(
            keys=original_values,
            values=tf.cast(converted_values, tf.int64),
            key_dtype=tf.string,
            value_dtype=tf.int64)
        table = tf.lookup.StaticHashTable(initializer, default_value=-1)
        return table.lookup(inputs[key])

    outputs = {}
    #欠損値を最頻値に変換
    inputs['workclass'] = tf.where(tf.equal(inputs['workclass'], '?'),
                                            'Private', inputs['workclass'])
    inputs['occupation'] = tf.where(tf.equal(inputs['occupation'], '?'),
                                             'Prof-specialty', inputs['occupation'])

    # TFTの関数を使って数値型の項目を正規化 (平均値0標準偏差1に変換)
    for key in NUMERIC_FEATURE_KEYS:
        outputs[transformed_name(key)] = tft.scale_to_z_score(inputs[key])

    # TFT の関数を使ってダミー変数化(One-Hot エンコーディング)
    for key in ONE_HOT_FEATURES.keys():
        dim = ONE_HOT_FEATURES[key]
        index = tft.compute_and_apply_vocabulary(
            tf.strings.strip(inputs[key]),
            num_oov_buckets=0,
            vocab_filename=key)
        one_hot_tensor = tf.one_hot(index, dim)
        one_hot_tensor = tf.reshape(one_hot_tensor, [-1, dim])
        for i in range(0, dim):
            one_hot_name = transformed_name(key + '_' + str(i))
            outputs[one_hot_name] = one_hot_tensor[:,i]
    # Labelを0と1に変換
    table_keys = ['<=50K', '>50K']
    outputs[transformed_name(LABEL_KEY)] = __convert_string2int_value(
             LABEL_KEY,  table_keys, [0, 1])

    return outputs

def stats_options_updater_fn(stats_type, stats_options):
    import tensorflow_data_validation as tfdv
    from tfx.components.transform import stats_options_util

    if stats_type == stats_options_util.StatsType.POST_TRANSFORM:
        load_post_schema = tfdv.load_schema_text('s3://census-income/post_schema/schema.pbtxt')
        stats_options.schema = load_post_schema
    return stats_options
