VALUES=('自由','独立','忠诚','尊重','平等','安全感','成就','亲密关系','自我实现','公平','真实')
def extract(text: str) -> dict:
    return {'dimension':'values','signals':[value for value in VALUES if value in text]}
