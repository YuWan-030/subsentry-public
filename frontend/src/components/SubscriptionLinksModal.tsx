import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Button, Empty, Grid, Image, Input, List, Modal, Space, Typography } from "antd";
import { CopyOutlined, LinkOutlined, QrcodeOutlined } from "@ant-design/icons";
import { fetchCustomerSubscription, type CustomerSubscription } from "../api/customers";
import { extractErrorMessage, notifyActionError, notifyActionSuccess } from "../utils/feedback";

const { useBreakpoint } = Grid;

type SubscriptionLinksModalProps = {
  customerId: string;
  open: boolean;
  onClose: () => void;
};

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

export default function SubscriptionLinksModal({ customerId, open, onClose }: SubscriptionLinksModalProps) {
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<CustomerSubscription | null>(null);
  const [qrOpen, setQrOpen] = useState(false);
  const [qrTitle, setQrTitle] = useState("");
  const [qrText, setQrText] = useState("");
  const [qrImage, setQrImage] = useState("");

  useEffect(() => {
    if (!open || !customerId) {
      return;
    }

    const load = async () => {
      setLoading(true);
      try {
        setData(await fetchCustomerSubscription(customerId));
      } catch (error: any) {
        notifyActionError("subscription-load", extractErrorMessage(error, "加载订阅链接失败"));
        setData(null);
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [customerId, open]);

  const localSubscriptionEnabled = Boolean(data?.local_subscription?.enabled);
  const linkPrefix = localSubscriptionEnabled ? "本地" : "3X-UI";
  const quickLinks = [
    { label: `${linkPrefix}标准订阅`, value: data?.links?.standard },
    { label: `${linkPrefix} JSON 订阅`, value: data?.links?.json },
    { label: `${linkPrefix} Clash 订阅`, value: data?.links?.clash },
  ].filter((item) => item.value);

  const handleCopy = async (text: string) => {
    await copyText(text);
    notifyActionSuccess("subscription-copy", "链接已复制");
  };

  const openQr = async (title: string, text: string) => {
    setQrTitle(title);
    setQrText(text);
    setQrImage(await QRCode.toDataURL(text, { margin: 2, width: isMobile ? 240 : 300 }));
    setQrOpen(true);
  };

  return (
    <Modal open={open} title="订阅链接" onCancel={onClose} footer={null} width={isMobile ? "calc(100vw - 24px)" : 760} destroyOnClose>
      <div style={{ minHeight: 180 }}>
        {loading ? (
          <Typography.Text type="secondary">正在加载订阅链接...</Typography.Text>
        ) : data ? (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <div>
              <Typography.Title level={5} style={{ marginBottom: 4 }}>{data.name}</Typography.Title>
              <Typography.Text type="secondary">订阅 ID：{data.sub_id || "未生成"} / {data.node}</Typography.Text>
            </div>

            <Space direction="vertical" size={10} style={{ width: "100%" }}>
              {quickLinks.map((item) => (
                <Input
                  key={item.label}
                  addonBefore={isMobile ? undefined : item.label}
                  prefix={isMobile ? <Typography.Text type="secondary">{item.label}</Typography.Text> : undefined}
                  value={item.value}
                  readOnly
                  style={{ width: "100%" }}
                  suffix={
                    <Space size={0}>
                      <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => void handleCopy(String(item.value))} />
                      <Button type="text" size="small" icon={<QrcodeOutlined />} onClick={() => void openQr(item.label, String(item.value))} />
                    </Space>
                  }
                />
              ))}
            </Space>

            {!localSubscriptionEnabled ? (
            <div>
              <Typography.Text strong>协议链接</Typography.Text>
              {data.protocol_links?.length ? (
                <List
                  size="small"
                  dataSource={data.protocol_links}
                  style={{ marginTop: 8 }}
                  renderItem={(item) => (
                    <List.Item
                      actions={[
                        <Button key="copy" type="link" size="small" icon={<CopyOutlined />} onClick={() => void handleCopy(item)}>复制</Button>,
                        <Button key="qr" type="link" size="small" icon={<QrcodeOutlined />} onClick={() => void openQr("协议链接", item)}>二维码</Button>,
                      ]}
                    >
                      <Typography.Text ellipsis style={{ maxWidth: isMobile ? 180 : 560 }}><LinkOutlined /> {item}</Typography.Text>
                    </List.Item>
                  )}
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无协议链接，可能客户未启用或订阅 ID 尚未生成" />
              )}
            </div>
            ) : null}
          </Space>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无订阅数据" />
        )}
      </div>
      <Modal open={qrOpen} title={`${qrTitle}二维码`} onCancel={() => setQrOpen(false)} footer={null} width={isMobile ? "calc(100vw - 32px)" : 380} destroyOnClose>
        <Space direction="vertical" size={12} style={{ width: "100%", alignItems: "center" }}>
          {qrImage ? <Image src={qrImage} preview={false} width={isMobile ? 240 : 300} /> : null}
          <Typography.Text copyable={{ text: qrText }} style={{ maxWidth: isMobile ? 240 : 320 }} ellipsis>{qrText}</Typography.Text>
        </Space>
      </Modal>
    </Modal>
  );
}
